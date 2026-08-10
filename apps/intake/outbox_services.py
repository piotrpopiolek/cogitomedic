from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from opentelemetry import trace

from apps.intake.models import (
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    IntakeOutboxEventType,
    IntakeOutboxStatus,
    IntakePdfStatus,
)
from apps.intake.pdf_builder import generate_intake_pdf
from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.integrations.hidrive.client import get_hidrive_adapter
from apps.operations.prom_metrics import record_outbox_execution
from apps.operations.services import create_audit_event
from apps.outbox.hidrive_paths import build_intake_hidrive_path
from apps.outbox.services import _try_delete_file

logger = logging.getLogger(__name__)

tracer = trace.get_tracer(__name__)


class IntakeOutboxEventNotRetryableError(DomainError):
    """Raised when manual retry is requested for non-retryable intake outbox event."""


@dataclass(frozen=True)
class IntakeOutboxProcessingResult:
    processed: int
    failed: int
    dead_lettered: int


def _execute_intake_outbox_event(event: IntakeOutboxEvent, *, now: datetime) -> None:
    with tracer.start_as_current_span(
        f"execute_intake_outbox_event_{event.event_type.lower()}",
        attributes={
            "outbox.stream": "intake",
            "intake_document_version_id": str(event.intake_document_version_id),
            "intake_outbox_event_id": str(event.id),
            "event_type": event.event_type,
        },
    ) as span:
        try:
            _execute_intake_outbox_event_internal(event, now=now)
        except Exception as e:
            span.record_exception(e)
            raise


def _execute_intake_outbox_event_internal(
    event: IntakeOutboxEvent, *, now: datetime
) -> None:
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

    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("cogito.intake_form_id", str(version.intake_form_id))

    if event.payload.get("simulate_error") is True:
        raise RuntimeError("Simulated intake outbox processing failure.")

    if event.event_type == IntakeOutboxEventType.GENERATE_INTAKE_PDF:
        version.pdf_generation_status = IntakePdfStatus.PROCESSING
        version.save(update_fields=["pdf_generation_status"])

        pdf_local_path, pdf_checksum_sha256 = generate_intake_pdf(version)
        version.pdf_generation_status = IntakePdfStatus.COMPLETED
        version.pdf_local_path = pdf_local_path
        version.pdf_checksum_sha256 = pdf_checksum_sha256
        version.save(
            update_fields=[
                "pdf_generation_status",
                "pdf_local_path",
                "pdf_checksum_sha256",
            ]
        )

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
        if not version.pdf_local_path:
            raise RuntimeError("Intake PDF local path is missing for HiDrive upload.")
        hidrive_path = build_intake_hidrive_path(version)
        full_path = Path(settings.MEDIA_ROOT) / version.pdf_local_path
        adapter = get_hidrive_adapter()
        adapter.upload(remote_path=hidrive_path, local_path=full_path)
        version.hidrive_path = hidrive_path
        version.hidrive_sent = True
        version.hidrive_sent_at = now
        version.save(update_fields=["hidrive_path", "hidrive_sent", "hidrive_sent_at"])

        intake_form = version.intake_form
        sig_path = intake_form.signature_file_path
        if sig_path:
            _try_delete_file(sig_path)
            intake_form.signature_file_path = None
            intake_form.save(update_fields=["signature_file_path", "updated_at"])
            create_audit_event(
                event_type="INTAKE_SIGNATURE_FILE_DELETED",
                patient_id=intake_form.queue_entry.patient_id,
                context_clinic_site_id=intake_form.queue_entry.daily_queue.clinic_site_id,
                metadata={
                    "intake_document_version_id": str(version.id),
                    "reason": "hidrive_confirmed",
                },
            )
        return

    raise RuntimeError(f"Unsupported intake outbox event type: {event.event_type}")


def _execute_event(event: IntakeOutboxEvent, *, now: datetime) -> None:
    """Backward-compatible name; delegates to traced implementation."""
    _execute_intake_outbox_event(event, now=now)


def process_intake_outbox_events(
    *,
    batch_size: int | None = None,
    now: datetime | None = None,
) -> IntakeOutboxProcessingResult:
    """Process pending/failed intake outbox events (commit-per-event)."""
    effective_now = now or timezone.now()
    effective_batch = batch_size or settings.OUTBOX_BATCH_SIZE

    processed = 0
    failed = 0
    dead_lettered = 0
    claimed_ids: set[uuid.UUID] = set()

    for _ in range(effective_batch):
        intake_processed_ok = False
        version_created_at = None
        intake_event_type = None
        event_id = None
        with transaction.atomic():
            qs = (
                IntakeOutboxEvent.objects.select_for_update(
                    skip_locked=True,
                    of=("self",),
                )
                .select_related(
                    "intake_document_version",
                    "intake_document_version__intake_form",
                    "intake_document_version__intake_form__queue_entry",
                    "intake_document_version__intake_form__queue_entry__daily_queue",
                )
                .filter(
                    status__in=[
                        IntakeOutboxStatus.PENDING,
                        IntakeOutboxStatus.FAILED,
                    ],
                    available_at__lte=effective_now,
                )
                .order_by("available_at", "created_at")
            )
            if claimed_ids:
                qs = qs.exclude(id__in=claimed_ids)
            event = qs.first()
            if event is None:
                break

            event_id = event.id
            claimed_ids.add(event_id)
            version = event.intake_document_version
            patient_id = version.intake_form.queue_entry.patient_id
            version_created_at = version.created_at
            intake_event_type = event.event_type
            sid = transaction.savepoint()
            try:
                event.status = IntakeOutboxStatus.PROCESSING
                event.locked_at = effective_now
                event.error_message = None
                event.save(
                    update_fields=[
                        "status",
                        "locked_at",
                        "error_message",
                        "updated_at",
                    ]
                )
                _execute_event(event, now=effective_now)
                event.status = IntakeOutboxStatus.PROCESSED
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
                transaction.savepoint_commit(sid)
                intake_processed_ok = True
                processed += 1
            except Exception as exc:
                transaction.savepoint_rollback(sid)
                ev = IntakeOutboxEvent.objects.select_related(
                    "intake_document_version",
                    "intake_document_version__intake_form",
                    "intake_document_version__intake_form__queue_entry",
                    "intake_document_version__intake_form__queue_entry__daily_queue",
                ).get(pk=event_id)
                version = ev.intake_document_version
                patient_id = version.intake_form.queue_entry.patient_id
                if ev.event_type == IntakeOutboxEventType.GENERATE_INTAKE_PDF:
                    IntakeDocumentVersion.objects.filter(
                        id=ev.intake_document_version_id
                    ).update(pdf_generation_status=IntakePdfStatus.FAILED)
                ev.retry_count += 1
                ev.locked_at = None
                ev.error_message = str(exc)
                if ev.retry_count >= ev.max_retries:
                    ev.status = IntakeOutboxStatus.DEAD_LETTER
                    dead_lettered += 1
                else:
                    ev.status = IntakeOutboxStatus.FAILED
                    backoff = settings.OUTBOX_BASE_BACKOFF_SECONDS * (
                        2 ** (ev.retry_count - 1)
                    )
                    ev.available_at = effective_now + timedelta(seconds=backoff)
                    failed += 1
                ev.save(
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
                        if ev.status == IntakeOutboxStatus.DEAD_LETTER
                        else "INTAKE_OUTBOX_EVENT_FAILED"
                    ),
                    patient_id=patient_id,
                    context_clinic_site_id=version.intake_form.queue_entry.daily_queue.clinic_site_id,
                    metadata={
                        "intake_document_version_id": str(version.id),
                        "intake_outbox_event_id": str(ev.id),
                        "event_type": ev.event_type,
                        "retry_count": ev.retry_count,
                        "error_message": ev.error_message or "",
                    },
                )
                if ev.status == IntakeOutboxStatus.DEAD_LETTER:
                    logger.warning(
                        "intake_outbox_event_dead_lettered",
                        extra={
                            "intake_outbox_event_id": str(ev.id),
                            "intake_document_version_id": str(version.id),
                            "event_type": ev.event_type,
                            "retry_count": ev.retry_count,
                            "error_message": ev.error_message or "",
                            "patient_id": str(patient_id),
                        },
                    )
                else:
                    logger.warning(
                        "intake_outbox_event_failed",
                        extra={
                            "intake_outbox_event_id": str(ev.id),
                            "intake_document_version_id": str(version.id),
                            "event_type": ev.event_type,
                            "retry_count": ev.retry_count,
                            "error_message": ev.error_message or "",
                            "patient_id": str(patient_id),
                        },
                    )
                try:
                    record_outbox_execution(
                        stream="intake",
                        event_type=ev.event_type,
                        result=(
                            "dead_letter"
                            if ev.status == IntakeOutboxStatus.DEAD_LETTER
                            else "failed"
                        ),
                        start_ts=None,
                        end_ts=None,
                    )
                except Exception:
                    logger.exception(
                        "record_outbox_execution failed after failed intake outbox event %s",
                        ev.id,
                    )

        if intake_processed_ok:
            try:
                record_outbox_execution(
                    stream="intake",
                    event_type=intake_event_type,
                    result="success",
                    start_ts=version_created_at,
                    end_ts=effective_now,
                )
            except Exception:
                logger.exception(
                    "record_outbox_execution failed after successful intake outbox event %s",
                    event_id,
                )

    logger.info(
        "intake_outbox_batch_finished",
        extra={
            "processed": processed,
            "failed": failed,
            "dead_lettered": dead_lettered,
            "batch_size": len(claimed_ids),
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
        raise IntakeOutboxEventNotRetryableError(
            domain_message("other.domain.outbox_event_not_retryable"),
            api_message_key="other.domain.outbox_event_not_retryable",
        )

    event.status = IntakeOutboxStatus.PENDING
    event.available_at = timezone.now()
    event.locked_at = None
    event.error_message = None
    event.save(
        update_fields=[
            "status",
            "available_at",
            "locked_at",
            "error_message",
            "updated_at",
        ]
    )

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
