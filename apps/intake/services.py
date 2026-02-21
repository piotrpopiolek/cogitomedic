from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError, StateTransitionError
from apps.intake.models import (
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.operations.services import create_audit_event
from apps.reception.models import QueueEntry, QueueEntryStatus


class RequiredConsentMissingError(DomainError):
    """Raised when required active consent is not accepted."""


class RequiredAnamnesisMissingError(DomainError):
    """Raised when required active anamnesis question has no answer."""


class IntakeSessionValidationError(DomainError):
    """Raised when intake submit session/token state is invalid."""


def _extract_answered_question_codes(anamnesis_payload: dict) -> set[str]:
    answers_raw = anamnesis_payload.get("answers", [])
    answered_codes: set[str] = set()
    if not isinstance(answers_raw, list):
        return answered_codes

    for answer in answers_raw:
        if not isinstance(answer, dict):
            continue
        question_code = answer.get("question_code")
        if not isinstance(question_code, str) or not question_code:
            continue

        selected_option_codes = answer.get("selected_option_codes")
        free_text = answer.get("free_text")

        has_selected_options = isinstance(selected_option_codes, list) and len(selected_option_codes) > 0
        has_free_text = isinstance(free_text, str) and bool(free_text.strip())
        if has_selected_options or has_free_text:
            answered_codes.add(question_code)

    return answered_codes


@transaction.atomic
def submit_patient_intake_form(
    *,
    intake_form_id: uuid.UUID,
    submitted_at: datetime | None = None,
    submitted_by_user_id: uuid.UUID | None = None,
) -> PatientIntakeForm:
    """
    Submit intake form with required consent/anamnesis validation.

    Transition is done atomically:
    - validates latest-wins active session state;
    - validates required active consents/anamnesis;
    - sets intake form to SUBMITTED;
    - marks the active session as consumed;
    - updates queue entry state to PATIENT_COMPLETED.
    """
    intake_form = (
        PatientIntakeForm.objects.select_for_update()
        .select_related("session", "queue_entry")
        .get(id=intake_form_id)
    )
    session = intake_form.session
    queue_entry = QueueEntry.objects.select_for_update().get(id=intake_form.queue_entry_id)
    now = submitted_at or timezone.now()

    if intake_form.form_status == IntakeStatus.SUBMITTED:
        return intake_form
    if intake_form.form_status != IntakeStatus.IN_PROGRESS:
        raise StateTransitionError("Only IN_PROGRESS intake form can be submitted.")
    if not intake_form.signature_file_path:
        raise StateTransitionError("Signature is required before intake submission.")

    if queue_entry.active_session_id != session.id:
        raise IntakeSessionValidationError("Session is not active for this queue entry.")
    if session.consumed_at is not None:
        raise IntakeSessionValidationError("Session has already been consumed.")
    if session.expires_at <= now:
        raise IntakeSessionValidationError("Session has expired.")

    required_consent_ids = set(
        ConsentDefinition.objects.filter(is_active=True, is_required=True).values_list("id", flat=True)
    )
    accepted_required_consent_ids = set(
        PatientIntakeConsent.objects.filter(
            intake_form_id=intake_form.id,
            consent_definition_id__in=required_consent_ids,
            accepted=True,
        ).values_list("consent_definition_id", flat=True)
    )
    missing_consent_ids = required_consent_ids - accepted_required_consent_ids
    if missing_consent_ids:
        raise RequiredConsentMissingError("Required active consents are not accepted.")

    required_question_codes = set(
        AnamnesisQuestionDefinition.objects.filter(
            is_active=True,
            is_required=True,
        ).values_list("code", flat=True)
    )
    answered_question_codes = _extract_answered_question_codes(intake_form.anamnesis_payload)
    missing_question_codes = required_question_codes - answered_question_codes
    if missing_question_codes:
        raise RequiredAnamnesisMissingError("Required active anamnesis questions are not answered.")

    intake_form.form_status = IntakeStatus.SUBMITTED
    intake_form.submitted_at = now
    intake_form.save(update_fields=["form_status", "submitted_at", "updated_at"])

    session.consumed_at = now
    session.save(update_fields=["consumed_at"])

    queue_entry.entry_status = QueueEntryStatus.PATIENT_COMPLETED
    queue_entry.save(update_fields=["entry_status", "updated_at"])

    create_audit_event(
        event_type="INTAKE_SUBMITTED",
        actor_user_id=submitted_by_user_id,
        patient_id=queue_entry.patient_id,
        metadata={
            "intake_form_id": str(intake_form.id),
            "queue_entry_id": str(queue_entry.id),
            "session_id": str(session.id),
        },
    )

    return intake_form


@transaction.atomic
def save_intake_anamnesis_payload(
    *,
    intake_form_id: uuid.UUID,
    anamnesis_schema_version: int,
    answers_payload: list[dict],
) -> PatientIntakeForm:
    """Persist validated anamnesis payload for in-progress intake form."""
    intake_form = PatientIntakeForm.objects.select_for_update().get(id=intake_form_id)
    if intake_form.form_status != IntakeStatus.IN_PROGRESS:
        raise StateTransitionError("Anamnesis can be edited only for IN_PROGRESS intake form.")

    intake_form.anamnesis_schema_version = anamnesis_schema_version
    intake_form.anamnesis_payload = {
        "schema_version": anamnesis_schema_version,
        "answers": answers_payload,
    }
    intake_form.save(update_fields=["anamnesis_schema_version", "anamnesis_payload", "updated_at"])
    return intake_form
