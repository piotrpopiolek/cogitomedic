from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.intake.models import (
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    IntakeOutboxEventType,
    IntakeOutboxStatus,
    IntakePdfStatus,
)
from apps.intake.pdf_builder import generate_intake_pdf
from apps.core.exceptions import DomainError
from apps.operations.services import create_audit_event
from apps.outbox.hidrive_paths import build_intake_hidrive_path

logger = logging.getLogger(__name__)


class IntakeOutboxEventNotRetryableError(DomainError):
    """Raised when manual retry is requested for non-retryable intake outbox event."""


@dataclass(frozen=True)
class IntakeOutboxProcessingResult:
    processed: int
    failed: int
    dead_lettered: int


def _execute_event(event: IntakeOutboxEvent, *, now: datetime) -> None:
    version = (
        IntakeDocumentVersion.objects.select_for_update()
        .select_related(
            "intake_form",
            "intake_form__queue_entry",
            "intake_form__queue_entry__patient",
            "intake_form__queue_entry__daily_queue",
        )
        .get(id=event.intake_document_version_id)
    )

    if event.payload.get("simulate_error") is True:
        raise RuntimeError("Simulated intake outbox processing failure.")

    if event.event_type == IntakeOutboxEventType.GENERATE_INTAKE_PDF:
        version.pdf_generation_status = IntakePdfStatus.PROCESSING
        version.save(update_fields=["pdf_generation_status"])

        pdf_local_path, pdf_checksum_sha256 = generate_intake_pdf(version)
        version.pdf_generation_status = IntakePdfStatus.COMPLETED
        version.pdf_local_path = pdf_local_path
        version.pdf_checksum_sha256 = pdf_checksum_sha256
        version.save(update_fields=["pdf_generation_status", "pdf_local_path", "pdf_checksum_sha256"])

        next_payload = {**event.payload, "intake_document_version_id": str(version.id)}
        IntakeOutboxEvent.objects.get_or_create(
            intake_document_version=version,
            event_type=IntakeOutboxEventType.HIDRIVE_UPLOAD_INTAKE_PDF,
            defaults={
                "aggregate_id": version.id,
                "payload_schema_version": 1,
                "payload": next_payload,
                "status": IntakeOutboxStatus.PENDING,
            },
        )
        return

    if event.event_type == IntakeOutboxEventType.HIDRIVE_UPLOAD_INTAKE_PDF:
        version.hidrive_path = build_intake_hidrive_path(version, now=now)
        version.hidrive_sent = True
        version.hidrive_sent_at = now
        version.save(update_fields=["hidrive_path", "hidrive_sent", "hidrive_sent_at"])
        return

    raise RuntimeError(f"Unsupported intake outbox event type: {event.event_type}")


@transaction.atomic
def process_intake_outbox_events(
    *,
    batch_size: int | None = None,
    now: datetime | None = None,
) -> IntakeOutboxProcessingResult:
    effective_now = now or timezone.now()
    effective_batch = batch_size or settings.OUTBOX_BATCH_SIZE
    events = list(
        IntakeOutboxEvent.objects.select_for_update(skip_locked=True)
        .filter(
            status__in=[IntakeOutboxStatus.PENDING, IntakeOutboxStatus.FAILED],
            available_at__lte=effective_now,
        )
        .order_by("available_at", "created_at")[:effective_batch]
    )

    processed = 0
    failed = 0
    dead_lettered = 0

    for event in events:
        event.status = IntakeOutboxStatus.PROCESSING
        event.locked_at = effective_now
        event.error_message = None
        event.save(update_fields=["status", "locked_at", "error_message", "updated_at"])

        version = event.intake_document_version
        patient_id = version.intake_form.queue_entry.patient_id
        try:
            with transaction.atomic():
                _execute_event(event, now=effective_now)
            event.status = IntakeOutboxStatus.PROCESSED
            event.processed_at = effective_now
            event.locked_at = None
            event.error_message = None
            event.save(update_fields=["status", "processed_at", "locked_at", "error_message", "updated_at"])
            create_audit_event(
                event_type="INTAKE_OUTBOX_EVENT_PROCESSED",
                patient_id=patient_id,
                context_clinic_site_id=version.intake_form.queue_entry.daily_queue.clinic_site_id,
                metadata={
                    "intake_document_version_id": str(version.id),
                    "intake_outbox_event_id": str(event.id),
                    "event_type": event.event_type,
                    "retry_count": event.retry_count,
                },
            )
            logger.info(
                "intake_outbox_event_processed",
                extra={
                    "intake_outbox_event_id": str(event.id),
                    "intake_document_version_id": str(version.id),
                    "event_type": event.event_type,
                    "patient_id": str(patient_id),
                },
            )
            processed += 1
        except Exception as exc:
            if event.event_type == IntakeOutboxEventType.GENERATE_INTAKE_PDF:
                IntakeDocumentVersion.objects.filter(id=event.intake_document_version_id).update(
                    pdf_generation_status=IntakePdfStatus.FAILED
                )
            event.retry_count += 1
            event.locked_at = None
            event.error_message = str(exc)
            if event.retry_count >= event.max_retries:
                event.status = IntakeOutboxStatus.DEAD_LETTER
                dead_lettered += 1
            else:
                event.status = IntakeOutboxStatus.FAILED
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
            create_audit_event(
                event_type=(
                    "INTAKE_OUTBOX_EVENT_DEAD_LETTERED"
                    if event.status == IntakeOutboxStatus.DEAD_LETTER
                    else "INTAKE_OUTBOX_EVENT_FAILED"
                ),
                patient_id=patient_id,
                context_clinic_site_id=version.intake_form.queue_entry.daily_queue.clinic_site_id,
                metadata={
                    "intake_document_version_id": str(version.id),
                    "intake_outbox_event_id": str(event.id),
                    "event_type": event.event_type,
                    "retry_count": event.retry_count,
                    "error_message": event.error_message or "",
                },
            )
            if event.status == IntakeOutboxStatus.DEAD_LETTER:
                logger.warning(
                    "intake_outbox_event_dead_lettered",
                    extra={
                        "intake_outbox_event_id": str(event.id),
                        "intake_document_version_id": str(version.id),
                        "event_type": event.event_type,
                        "retry_count": event.retry_count,
                        "error_message": event.error_message or "",
                        "patient_id": str(patient_id),
                    },
                )
            else:
                logger.warning(
                    "intake_outbox_event_failed",
                    extra={
                        "intake_outbox_event_id": str(event.id),
                        "intake_document_version_id": str(version.id),
                        "event_type": event.event_type,
                        "retry_count": event.retry_count,
                        "error_message": event.error_message or "",
                        "patient_id": str(patient_id),
                    },
                )

    logger.info(
        "intake_outbox_batch_finished",
        extra={
            "processed": processed,
            "failed": failed,
            "dead_lettered": dead_lettered,
            "batch_size": len(events),
        },
    )
    return IntakeOutboxProcessingResult(
        processed=processed,
        failed=failed,
        dead_lettered=dead_lettered,
    )


@transaction.atomic
def retry_intake_outbox_event(
    *,
    event: IntakeOutboxEvent,
    reason: str,
    actor_user_id: uuid.UUID | None = None,
) -> IntakeOutboxEvent:
    """Move FAILED/DEAD_LETTER intake outbox event back to PENDING for manual retry."""
    event = (
        IntakeOutboxEvent.objects.select_for_update()
        .select_related(
            "intake_document_version",
            "intake_document_version__intake_form",
            "intake_document_version__intake_form__queue_entry",
            "intake_document_version__intake_form__queue_entry__daily_queue",
        )
        .get(id=event.id)
    )
    if event.status not in [IntakeOutboxStatus.FAILED, IntakeOutboxStatus.DEAD_LETTER]:
        raise IntakeOutboxEventNotRetryableError("Event is not retryable in current status.")

    event.status = IntakeOutboxStatus.PENDING
    event.available_at = timezone.now()
    event.locked_at = None
    event.error_message = None
    event.save(update_fields=["status", "available_at", "locked_at", "error_message", "updated_at"])

    version = event.intake_document_version
    patient_id = version.intake_form.queue_entry.patient_id
    create_audit_event(
        event_type="INTAKE_OUTBOX_EVENT_RETRY_REQUESTED",
        actor_user_id=actor_user_id,
        patient_id=patient_id,
        context_clinic_site_id=version.intake_form.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "intake_document_version_id": str(version.id),
            "intake_outbox_event_id": str(event.id),
            "event_type": event.event_type,
            "reason": reason,
        },
    )
    logger.info(
        "intake_outbox_event_retry_requested",
        extra={
            "intake_outbox_event_id": str(event.id),
            "intake_document_version_id": str(version.id),
            "event_type": event.event_type,
            "reason": reason,
            "patient_id": str(patient_id),
        },
    )
    return event
