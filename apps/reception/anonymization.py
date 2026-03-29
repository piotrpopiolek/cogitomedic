"""RODO Art. 17-style patient anonymization: DB phases + filesystem cleanup outside long transactions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.core.retention_payloads import ANONYMIZED_INTAKE_SNAPSHOT
from apps.intake.models import IntakeDocumentVersion, PatientIntakeConsent, PatientIntakeForm
from apps.medical.models import MedicalDocumentVersion
from apps.operations.services import create_audit_event
from apps.outbox.services import _try_delete_file
from apps.reception.models import Patient, QueueEntry, QueueEntryStatus


_TERMINAL_QUEUE_STATUSES = frozenset(
    {
        QueueEntryStatus.PUBLISHED,
        QueueEntryStatus.CANCELLED,
    }
)


def _now() -> datetime:
    return timezone.now()


def _extract_consent_summary(patient_id: uuid.UUID) -> dict[str, Any]:
    latest_form = (
        PatientIntakeForm.objects.filter(queue_entry__patient_id=patient_id)
        .select_related("queue_entry__daily_queue")
        .order_by("-submitted_at", "-created_at")
        .first()
    )
    if not latest_form or not latest_form.submitted_at:
        return {
            "schema_version": 1,
            "extracted_at": _now().isoformat(),
            "intake_form_id": None,
            "consents": [],
        }
    queue_date = latest_form.queue_entry.daily_queue.queue_date
    rows = PatientIntakeConsent.objects.filter(intake_form=latest_form).select_related(
        "consent_definition",
    )
    consents: list[dict[str, Any]] = []
    for c in rows:
        consents.append(
            {
                "code": c.consent_definition.code,
                "version": c.consent_definition.version,
                "accepted": c.accepted,
                "accepted_at": c.accepted_at.isoformat() if c.accepted_at else None,
                "intake_form_id": str(latest_form.id),
                "queue_date": queue_date.isoformat(),
            }
        )
    return {
        "schema_version": 1,
        "extracted_at": _now().isoformat(),
        "intake_form_id": str(latest_form.id),
        "consents": consents,
    }


def _delete_signature_files(patient_id: uuid.UUID) -> None:
    paths = list(
        PatientIntakeForm.objects.filter(queue_entry__patient_id=patient_id)
        .exclude(signature_file_path__isnull=True)
        .exclude(signature_file_path="")
        .values_list("signature_file_path", flat=True)
    )
    for p in paths:
        _try_delete_file(p)
    PatientIntakeForm.objects.filter(queue_entry__patient_id=patient_id).update(signature_file_path=None)


@transaction.atomic
def _phase1_begin(patient_id: uuid.UUID) -> tuple[Patient, bool]:
    patient = Patient.objects.select_for_update().get(id=patient_id)

    if patient.anonymized_at:
        return patient, False

    if not patient.anonymization_started_at:
        consent_summary = _extract_consent_summary(patient_id)
        PatientIntakeForm.objects.filter(queue_entry__patient_id=patient_id).update(
            anamnesis_payload={},
            body_map_data=[],
        )
        IntakeDocumentVersion.objects.filter(
            intake_form__queue_entry__patient_id=patient_id,
        ).update(snapshot_payload=dict(ANONYMIZED_INTAKE_SNAPSHOT))
        Patient.objects.filter(id=patient_id).update(
            consent_summary=consent_summary,
            anonymization_started_at=_now(),
        )

    patient.refresh_from_db()
    return patient, True


def _phase2_delete_files(patient_id: uuid.UUID) -> None:
    _delete_signature_files(patient_id)
    now_ts = _now()
    for v in MedicalDocumentVersion.objects.filter(
        medical_document__queue_entry__patient_id=patient_id,
        anonymization_deleted_at__isnull=True,
    ):
        if v.pdf_local_path:
            _try_delete_file(v.pdf_local_path)
        MedicalDocumentVersion.objects.filter(id=v.id).update(
            pdf_local_path=None,
            anonymization_deleted_at=now_ts,
        )
    for v in IntakeDocumentVersion.objects.filter(
        intake_form__queue_entry__patient_id=patient_id,
        anonymization_deleted_at__isnull=True,
    ):
        if v.pdf_local_path:
            _try_delete_file(v.pdf_local_path)
        IntakeDocumentVersion.objects.filter(id=v.id).update(
            pdf_local_path=None,
            anonymization_deleted_at=now_ts,
        )


@transaction.atomic
def _phase3_finalize(patient_id: uuid.UUID, *, actor_user_id: uuid.UUID) -> Patient:
    patient = Patient.objects.select_for_update().get(id=patient_id)
    if patient.anonymized_at:
        return patient

    phone_sentinel = str(patient_id.int)[:20]
    Patient.objects.filter(id=patient_id).update(
        first_name="ANONYMIZED",
        last_name="ANONYMIZED",
        phone=phone_sentinel,
        email=f"anon-{patient_id}@deleted.invalid",
        date_of_birth=None,
        street=None,
        city=None,
        postal_code=None,
        doctolib_patient_id=None,
        anonymized_at=_now(),
    )
    create_audit_event(
        event_type="PATIENT_ANONYMIZED",
        actor_user_id=actor_user_id,
        patient_id=patient_id,
        metadata={"_ref": {"patient_id": str(patient_id)}},
    )
    return Patient.objects.get(id=patient_id)


def anonymize_patient(patient_id: uuid.UUID, *, actor_user_id: uuid.UUID) -> Patient:
    active_count = (
        QueueEntry.objects.filter(patient_id=patient_id)
        .exclude(entry_status__in=_TERMINAL_QUEUE_STATUSES)
        .count()
    )
    if active_count > 0:
        raise DomainError(
            domain_message("other.domain.anonymization_patient_has_active_visits"),
            api_message_key="other.domain.anonymization_patient_has_active_visits",
        )

    patient, should_continue = _phase1_begin(patient_id)
    if not should_continue:
        return patient
    _phase2_delete_files(patient_id)
    return _phase3_finalize(patient_id, actor_user_id=actor_user_id)
