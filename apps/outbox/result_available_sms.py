"""Enqueue SMS_SEND (result available) for a patient without republishing."""

from __future__ import annotations

import uuid
from datetime import timedelta

import phonenumbers
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from phonenumbers import NumberParseException

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.medical.models import DocVersionStatus, MedicalDocumentVersion, PdfStatus
from apps.operations.services import create_audit_event
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.reception.models import Patient
from apps.reception.phone_utils import (
    SUPPORTED_SMS_REGIONS,
    format_phone_e164_for_sms,
)


def _assert_phone_supported_for_sms(phone: str) -> str:
    """Return E.164 when phone is valid in a supported SMS region; else raise."""
    trimmed = (phone or "").strip()
    if not trimmed:
        raise DomainError(
            domain_message("other.domain.patient_phone_required_sms"),
            api_message_key="other.domain.patient_phone_required_sms",
        )
    e164 = format_phone_e164_for_sms(trimmed)
    if not e164:
        raise DomainError(
            domain_message("other.domain.patient_phone_not_supported_for_sms"),
            api_message_key="other.domain.patient_phone_not_supported_for_sms",
        )
    try:
        parsed = phonenumbers.parse(e164, None)
    except NumberParseException as exc:
        raise DomainError(
            domain_message("other.domain.patient_phone_not_supported_for_sms"),
            api_message_key="other.domain.patient_phone_not_supported_for_sms",
        ) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise DomainError(
            domain_message("other.domain.patient_phone_not_supported_for_sms"),
            api_message_key="other.domain.patient_phone_not_supported_for_sms",
        )
    region = phonenumbers.region_code_for_number(parsed)
    if region not in SUPPORTED_SMS_REGIONS:
        raise DomainError(
            domain_message("other.domain.patient_phone_not_supported_for_sms"),
            api_message_key="other.domain.patient_phone_not_supported_for_sms",
        )
    return e164


def _latest_published_version_in_retention(
    patient_id: uuid.UUID,
) -> MedicalDocumentVersion | None:
    retention_days = int(getattr(settings, "PDF_RETENTION_DAYS", 60) or 60)
    threshold = timezone.now() - timedelta(days=retention_days)
    return (
        MedicalDocumentVersion.objects.filter(
            medical_document__queue_entry__patient_id=patient_id,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            revoked_at__isnull=True,
            anonymization_deleted_at__isnull=True,
            local_pdf_deleted_at__isnull=True,
            published_at__isnull=False,
            published_at__gte=threshold,
            version_no=F("medical_document__published_version_no"),
        )
        .select_related(
            "medical_document",
            "medical_document__queue_entry",
            "medical_document__queue_entry__daily_queue",
            "medical_document__queue_entry__patient",
        )
        .order_by("-published_at")
        .first()
    )


@transaction.atomic
def enqueue_result_available_sms_for_patient(
    *,
    patient_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> OutboxEvent:
    """
    Queue (or requeue) SMS_SEND with resend_sms=True for the patient's latest
    non-revoked published Befund still inside the retention window.

    Does not republish. Unique (version, SMS_SEND) is reused: PROCESSED / FAILED /
    DEAD_LETTER are moved back to PENDING with resend_sms=True.
    """
    try:
        patient = Patient.objects.select_for_update().get(id=patient_id)
    except Patient.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.patient_not_found"),
            api_message_key="other.api.patient_not_found",
        ) from exc

    e164 = _assert_phone_supported_for_sms(patient.phone or "")

    version = _latest_published_version_in_retention(patient.id)
    if version is None:
        raise DomainError(
            domain_message("other.domain.patient_no_published_result_for_sms"),
            api_message_key="other.domain.patient_no_published_result_for_sms",
        )

    version = MedicalDocumentVersion.objects.select_for_update().get(id=version.id)

    payload = {
        "medical_document_id": str(version.medical_document_id),
        "medical_document_version_id": str(version.id),
        "resend_sms": True,
        "source": "admin_patient_result_available_sms",
    }

    event, created = OutboxEvent.objects.select_for_update().get_or_create(
        medical_document_version=version,
        event_type=OutboxEventType.SMS_SEND,
        defaults={
            "aggregate_id": version.id,
            "payload_schema_version": 1,
            "payload": payload,
            "status": OutboxStatus.PENDING,
        },
    )

    if not created:
        if event.status == OutboxStatus.PROCESSING:
            raise DomainError(
                domain_message("other.domain.sms_send_already_processing"),
                api_message_key="other.domain.sms_send_already_processing",
            )
        merged = dict(event.payload or {})
        merged.update(payload)
        event.payload = merged
        event.status = OutboxStatus.PENDING

        event.retry_count = 0
        event.available_at = timezone.now()
        event.locked_at = None
        event.error_message = None
        event.processed_at = None
        event.save(
            update_fields=[
                "payload",
                "status",
                "retry_count",
                "available_at",
                "locked_at",
                "error_message",
                "processed_at",
                "updated_at",
            ]
        )

    create_audit_event(
        event_type="PATIENT_RESULT_AVAILABLE_SMS_ENQUEUED",
        actor_user_id=actor_user_id,
        patient_id=patient.id,
        medical_document_id=version.medical_document_id,
        outbox_event_id=event.id,
        context_clinic_site_id=version.medical_document.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            "phone_e164": e164,
            "outbox_event_created": created,
            "source": "admin_patient_result_available_sms",
        },
    )
    return event
