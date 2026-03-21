from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from opentelemetry import trace
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.integrations.sms.client import get_sms_adapter, get_sms_patient_results_text
from apps.medical.pdf_builder import generate_befund_pdf
from apps.medical.models import DocVersionStatus, MedicalDocumentVersion, PdfStatus
from apps.operations.services import create_audit_event
from apps.outbox.hidrive_paths import build_befund_hidrive_path
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus


@dataclass(frozen=True)
class OutboxProcessingResult:
    processed: int
    failed: int
    dead_lettered: int


@dataclass(frozen=True)
class RetentionCleanupResult:
    candidates: int
    deleted: int
    skipped_not_safe: int


class OutboxEventNotRetryableError(DomainError):
    """Raised when manual retry is requested for non-retryable event."""

tracer = trace.get_tracer(__name__)


def _execute_event(event: OutboxEvent, *, now: datetime) -> None:
    with tracer.start_as_current_span(
        f"execute_outbox_event_{event.event_type.lower()}",
        attributes={
            "medical_document_version_id": str(event.medical_document_version_id),
            "outbox_event_id": str(event.id),
            "event_type": event.event_type,
        }
    ) as span:
        try:
            _execute_event_internal(event, now=now)
        except Exception as e:
            span.record_exception(e)
            raise

def _execute_event_internal(event: OutboxEvent, *, now: datetime) -> None:
    version = (
        MedicalDocumentVersion.objects.select_for_update()
        .select_related(
            "medical_document",
            "medical_document__queue_entry",
            "medical_document__queue_entry__patient",
            "medical_document__intake_form",
            "medical_document__intake_form__session",
        )
        .get(id=event.medical_document_version_id)
    )

    if event.payload.get("simulate_error") is True:
        raise RuntimeError("Simulated outbox processing failure.")

    if event.event_type == OutboxEventType.GENERATE_PDF:
        version.pdf_generation_status = PdfStatus.PROCESSING
        version.save(update_fields=["pdf_generation_status"])

        pdf_local_path, pdf_checksum_sha256 = generate_befund_pdf(version)
        version.pdf_generation_status = PdfStatus.COMPLETED
        version.pdf_local_path = pdf_local_path
        version.pdf_checksum_sha256 = pdf_checksum_sha256
        version.save(update_fields=["pdf_generation_status", "pdf_local_path", "pdf_checksum_sha256"])
        next_payload = {**event.payload, "medical_document_version_id": str(version.id)}
        OutboxEvent.objects.get_or_create(
            medical_document_version=version,
            event_type=OutboxEventType.HIDRIVE_UPLOAD,
            defaults={
                "aggregate_id": version.id,
                "payload_schema_version": 1,
                "payload": next_payload,
                "status": OutboxStatus.PENDING,
            },
        )
        return

    if event.event_type == OutboxEventType.HIDRIVE_UPLOAD:
        version.hidrive_path = build_befund_hidrive_path(version)
        version.hidrive_sent = True
        version.hidrive_sent_at = now
        version.save(update_fields=["hidrive_path", "hidrive_sent", "hidrive_sent_at"])
        next_payload = {**event.payload, "medical_document_version_id": str(version.id)}
        OutboxEvent.objects.get_or_create(
            medical_document_version=version,
            event_type=OutboxEventType.SMS_SEND,
            defaults={
                "aggregate_id": version.id,
                "payload_schema_version": 1,
                "payload": next_payload,
                "status": OutboxStatus.PENDING,
            },
        )
        return

    if event.event_type == OutboxEventType.SMS_SEND:
        resend_sms = event.payload.get("resend_sms") is True
        if not resend_sms:
            other_version_sent = MedicalDocumentVersion.objects.filter(
                medical_document_id=version.medical_document_id,
                sms_sent=True,
            ).exclude(id=version.id).exists()
            if other_version_sent:
                version.sms_sent = False
                version.save(update_fields=["sms_sent"])
                return

        patient = version.medical_document.queue_entry.patient
        if not (patient.phone or "").strip():
            raise DomainError("Patient has no phone number; cannot send SMS.")
        base_url = getattr(settings, "PATIENT_RESULTS_BASE_URL", "https://ergebnisse.cogitomedica.pl")
        form_locale = None
        intake_form = version.medical_document.intake_form
        if intake_form and intake_form.session_id:
            form_locale = intake_form.session.form_locale
        sms_text = get_sms_patient_results_text(form_locale, base_url)
        adapter = get_sms_adapter()
        adapter.send_sms(to=patient.phone, message=sms_text)

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
            doc = event.medical_document_version.medical_document
            create_audit_event(
                event_type="OUTBOX_EVENT_PROCESSED",
                patient_id=doc.queue_entry.patient_id,
                medical_document_id=doc.id,
                outbox_event_id=event.id,
                context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
                metadata={
                    "event_type": event.event_type,
                    "retry_count": event.retry_count,
                },
            )
            processed += 1
        except Exception as exc:
            if event.event_type == OutboxEventType.GENERATE_PDF:
                MedicalDocumentVersion.objects.filter(id=event.medical_document_version_id).update(
                    pdf_generation_status=PdfStatus.FAILED
                )
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
            doc = event.medical_document_version.medical_document
            create_audit_event(
                event_type=(
                    "OUTBOX_EVENT_DEAD_LETTERED"
                    if event.status == OutboxStatus.DEAD_LETTER
                    else "OUTBOX_EVENT_FAILED"
                ),
                patient_id=doc.queue_entry.patient_id,
                medical_document_id=doc.id,
                outbox_event_id=event.id,
                context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
                metadata={
                    "event_type": event.event_type,
                    "retry_count": event.retry_count,
                    "error_message": event.error_message or "",
                },
            )

    return OutboxProcessingResult(
        processed=processed,
        failed=failed,
        dead_lettered=dead_lettered,
    )


@transaction.atomic
def retry_outbox_event(
    *,
    event: OutboxEvent,
    reason: str,
    actor_user_id: uuid.UUID | None = None,
) -> OutboxEvent:
    """Move FAILED/DEAD_LETTER event back to PENDING for manual retry."""
    event = (
        OutboxEvent.objects.select_for_update()
        .select_related(
            "medical_document_version__medical_document__queue_entry__daily_queue",
        )
        .get(id=event.id)
    )
    if event.status not in [OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER]:
        raise OutboxEventNotRetryableError("Event is not retryable in current status.")

    event.status = OutboxStatus.PENDING
    event.available_at = timezone.now()
    event.locked_at = None
    event.error_message = None
    event.save(update_fields=["status", "available_at", "locked_at", "error_message", "updated_at"])

    create_audit_event(
        event_type="OUTBOX_EVENT_RETRY_REQUESTED",
        actor_user_id=actor_user_id,
        patient_id=event.medical_document_version.medical_document.queue_entry.patient_id,
        medical_document_id=event.medical_document_version.medical_document_id,
        outbox_event_id=event.id,
        context_clinic_site_id=event.medical_document_version.medical_document.queue_entry.daily_queue.clinic_site_id,
        metadata={"event_type": event.event_type, "reason": reason},
    )
    return event


def _try_delete_file(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(settings.MEDIA_ROOT) / path
    if path.exists() and path.is_file():
        path.unlink()


@transaction.atomic
def run_retention_cleanup(*, older_than_days: int = 30, dry_run: bool = True) -> RetentionCleanupResult:
    """Delete local PDFs for safe, old published versions."""
    if older_than_days <= 0:
        raise DomainError("older_than_days must be positive.")

    threshold = timezone.now() - timedelta(days=older_than_days)
    candidates = list(
        MedicalDocumentVersion.objects.select_for_update()
        .select_related(
            "medical_document__queue_entry__daily_queue",
        )
        .filter(
            version_status=DocVersionStatus.PUBLISHED,
            published_at__isnull=False,
            published_at__lte=threshold,
            local_pdf_deleted_at__isnull=True,
        )
        .order_by("published_at")
    )

    deleted = 0
    skipped_not_safe = 0
    now = timezone.now()

    for version in candidates:
        if not (version.hidrive_sent and version.sms_sent):
            skipped_not_safe += 1
            create_audit_event(
                event_type="RETENTION_FILE_SKIPPED",
                patient_id=version.medical_document.queue_entry.patient_id,
                medical_document_id=version.medical_document_id,
                context_clinic_site_id=version.medical_document.queue_entry.daily_queue.clinic_site_id,
                metadata={
                    "medical_document_version_id": str(version.id),
                    "reason": "NOT_SAFE_FOR_DELETION",
                },
            )
            continue

        if dry_run:
            continue

        _try_delete_file(version.pdf_local_path)
        version.local_pdf_deleted_at = now
        version.pdf_local_path = None
        version.save(update_fields=["local_pdf_deleted_at", "pdf_local_path"])
        deleted += 1

        create_audit_event(
            event_type="RETENTION_FILE_DELETED",
            patient_id=version.medical_document.queue_entry.patient_id,
            medical_document_id=version.medical_document_id,
            context_clinic_site_id=version.medical_document.queue_entry.daily_queue.clinic_site_id,
            metadata={
                "medical_document_version_id": str(version.id),
                "older_than_days": older_than_days,
            },
        )

    return RetentionCleanupResult(
        candidates=len(candidates),
        deleted=deleted,
        skipped_not_safe=skipped_not_safe,
    )
