from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.medical.models import MedicalDocumentVersion, PdfStatus
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus


@dataclass(frozen=True)
class OutboxProcessingResult:
    processed: int
    failed: int
    dead_lettered: int


def _build_hidrive_path(version: MedicalDocumentVersion) -> str:
    return f"/hidrive/medical/{version.medical_document_id}/{version.id}.pdf"


def _execute_event(event: OutboxEvent, *, now: datetime) -> None:
    version = MedicalDocumentVersion.objects.select_for_update().get(id=event.medical_document_version_id)

    if event.payload.get("simulate_error") is True:
        raise RuntimeError("Simulated outbox processing failure.")

    if event.event_type == OutboxEventType.GENERATE_PDF:
        version.pdf_generation_status = PdfStatus.COMPLETED
        version.pdf_local_path = f"/tmp/pdfs/{version.id}.pdf"
        version.pdf_checksum_sha256 = "a" * 64
        version.save(update_fields=["pdf_generation_status", "pdf_local_path", "pdf_checksum_sha256"])
        OutboxEvent.objects.get_or_create(
            medical_document_version=version,
            event_type=OutboxEventType.HIDRIVE_UPLOAD,
            defaults={
                "aggregate_id": version.id,
                "payload_schema_version": 1,
                "payload": {"medical_document_version_id": str(version.id)},
                "status": OutboxStatus.PENDING,
            },
        )
        return

    if event.event_type == OutboxEventType.HIDRIVE_UPLOAD:
        version.hidrive_path = _build_hidrive_path(version)
        version.hidrive_sent = True
        version.hidrive_sent_at = now
        version.save(update_fields=["hidrive_path", "hidrive_sent", "hidrive_sent_at"])
        OutboxEvent.objects.get_or_create(
            medical_document_version=version,
            event_type=OutboxEventType.SMS_SEND,
            defaults={
                "aggregate_id": version.id,
                "payload_schema_version": 1,
                "payload": {"medical_document_version_id": str(version.id)},
                "status": OutboxStatus.PENDING,
            },
        )
        return

    if event.event_type == OutboxEventType.SMS_SEND:
        version.sms_sent = True
        version.sms_sent_at = now
        version.save(update_fields=["sms_sent", "sms_sent_at"])
        return

    raise RuntimeError(f"Unsupported outbox event type: {event.event_type}")


@transaction.atomic
def process_outbox_events(*, batch_size: int | None = None, now: datetime | None = None) -> OutboxProcessingResult:
    """Process pending/failed outbox events available for execution."""
    effective_now = now or timezone.now()
    effective_batch = batch_size or settings.OUTBOX_BATCH_SIZE

    events = list(
        OutboxEvent.objects.select_for_update(skip_locked=True)
        .filter(
            status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED],
            available_at__lte=effective_now,
        )
        .order_by("available_at", "created_at")[:effective_batch]
    )

    processed = 0
    failed = 0
    dead_lettered = 0

    for event in events:
        event.status = OutboxStatus.PROCESSING
        event.locked_at = effective_now
        event.error_message = None
        event.save(update_fields=["status", "locked_at", "error_message", "updated_at"])

        try:
            _execute_event(event, now=effective_now)
            event.status = OutboxStatus.PROCESSED
            event.processed_at = effective_now
            event.locked_at = None
            event.error_message = None
            event.save(
                update_fields=[
                    "status",
                    "processed_at",
                    "locked_at",
                    "error_message",
                    "updated_at",
                ]
            )
            processed += 1
        except Exception as exc:
            event.retry_count += 1
            event.locked_at = None
            event.error_message = str(exc)
            if event.retry_count >= event.max_retries:
                event.status = OutboxStatus.DEAD_LETTER
                dead_lettered += 1
            else:
                event.status = OutboxStatus.FAILED
                backoff = settings.OUTBOX_BASE_BACKOFF_SECONDS * (2 ** (event.retry_count - 1))
                event.available_at = effective_now + timedelta(seconds=backoff)
                failed += 1
            event.save(
                update_fields=[
                    "status",
                    "retry_count",
                    "locked_at",
                    "error_message",
                    "available_at",
                    "updated_at",
                ]
            )

    return OutboxProcessingResult(
        processed=processed,
        failed=failed,
        dead_lettered=dead_lettered,
    )
