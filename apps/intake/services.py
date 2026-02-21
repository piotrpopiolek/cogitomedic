from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import DomainError, StateTransitionError
from apps.intake.models import (
    AnamnesisOptionDefinition,
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


class ConsentNotActiveError(DomainError):
    """Raised when a consent definition is not active for the current date."""


class InvalidSignatureError(DomainError):
    """Raised when signature payload is invalid or too large."""


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


def _effective_consent_filter(today: date):
    return Q(is_active=True) & Q(effective_from__lte=today) & (Q(effective_to__isnull=True) | Q(effective_to__gte=today))


def _effective_question_filter(today: date):
    return Q(is_active=True) & Q(effective_from__lte=today) & (Q(effective_to__isnull=True) | Q(effective_to__gte=today))


def get_intake_form_context(
    *,
    intake_form_id: uuid.UUID,
    form_locale: str = "de-DE",
    tablet_restrict_to_today: bool = False,
) -> dict[str, Any]:
    """
    Build intake form context for tablet/verification screen.

    Returns patient (read-only), consents with accepted state, anamnesis questions
    with options and current answer, body_map and form status.
    Raises ObjectDoesNotExist if form not found.
    For tablet_restrict_to_today=True (TABLET role), returns 404 when queue is not today.
    """
    from django.core.exceptions import ObjectDoesNotExist

    today = timezone.now().date()
    intake_form = (
        PatientIntakeForm.objects.select_related(
            "session",
            "queue_entry",
            "queue_entry__patient",
            "queue_entry__daily_queue",
        )
        .get(id=intake_form_id)
    )
    if tablet_restrict_to_today and intake_form.queue_entry.daily_queue.queue_date != today:
        raise ObjectDoesNotExist("Intake form queue is not from today.")
    session = intake_form.session
    queue_entry = intake_form.queue_entry
    patient = queue_entry.patient

    # Consent definitions effective today; then merge with intake form's consent choices
    consent_defs = (
        ConsentDefinition.objects.filter(_effective_consent_filter(today))
        .order_by("display_order", "code")
        .values("id", "code", "title_de", "content_de", "is_required")
    )
    consent_by_def_id = {
        c.consent_definition_id: c
        for c in PatientIntakeConsent.objects.filter(intake_form_id=intake_form.id).select_related(
            "consent_definition"
        )
    }
    consents_payload = []
    for cd in consent_defs:
        cd_id = cd["id"]
        pic = consent_by_def_id.get(cd_id)
        consents_payload.append({
            "consent_definition_id": str(cd_id),
            "code": cd["code"],
            "title_de": cd["title_de"],
            "is_required": cd["is_required"],
            "accepted": pic.accepted if pic else False,
            "accepted_at": pic.accepted_at.isoformat() if pic and pic.accepted_at else None,
        })

    # Anamnesis questions effective today with options; attach current answer from payload
    question_defs = (
        AnamnesisQuestionDefinition.objects.filter(_effective_question_filter(today))
        .prefetch_related("options")
        .order_by("display_order", "code")
    )
    answers_raw = intake_form.anamnesis_payload.get("answers") or []
    answer_by_code = {a.get("question_code"): a for a in answers_raw if isinstance(a, dict) and a.get("question_code")}

    def option_label(opt: AnamnesisOptionDefinition) -> str:
        return opt.option_text_de if form_locale.startswith("de") else opt.option_text_en

    def question_text(q: AnamnesisQuestionDefinition) -> str:
        return q.question_text_de if form_locale.startswith("de") else q.question_text_en

    anamnesis_questions_payload = []
    for q in question_defs:
        if not q.is_active:
            continue
        options = [{"option_code": o.code, "label": option_label(o)} for o in q.options.filter(is_active=True).order_by("display_order", "code")]
        current = answer_by_code.get(q.code) or {}
        answer = {
            "selected_option_codes": current.get("selected_option_codes") or [],
            "free_text": current.get("free_text"),
        }
        anamnesis_questions_payload.append({
            "question_code": q.code,
            "question_text": question_text(q),
            "answer_type": q.answer_type,
            "is_required": q.is_required,
            "options": options,
            "answer": answer,
        })

    # Patient (read-only for verification)
    patient_payload = {
        "id": str(patient.id),
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": patient.date_of_birth.isoformat(),
        "phone": patient.phone,
        "email": patient.email,
    }

    return {
        "intake_form_id": str(intake_form.id),
        "queue_entry_id": str(queue_entry.id),
        "form_status": intake_form.form_status,
        "form_locale": session.form_locale,
        "anamnesis_schema_version": intake_form.anamnesis_schema_version,
        "anamnesis_questions": anamnesis_questions_payload,
        "body_map_schema_version": intake_form.body_map_schema_version,
        "body_map_data": intake_form.body_map_data,
        "consents": consents_payload,
        "patient": patient_payload,
        "has_signature": bool(intake_form.signature_file_path),
    }


@transaction.atomic
def save_intake_consents(
    *,
    intake_form_id: uuid.UUID,
    consents_payload: list[dict],
) -> PatientIntakeForm:
    """
    Replace consent acceptance set for an in-progress intake form.

    Each item: consent_definition_id (UUID), accepted (bool).
    Raises ConsentNotActiveError if any consent definition is not active for today.
    """
    today = timezone.now().date()
    effective_ids = set(
        ConsentDefinition.objects.filter(_effective_consent_filter(today)).values_list("id", flat=True)
    )
    now = timezone.now()

    intake_form = PatientIntakeForm.objects.select_for_update().get(id=intake_form_id)
    if intake_form.form_status != IntakeStatus.IN_PROGRESS:
        raise StateTransitionError("Consents can be edited only for IN_PROGRESS intake form.")

    for item in consents_payload:
        cdef_id = item.get("consent_definition_id")
        if cdef_id not in effective_ids:
            raise ConsentNotActiveError(
                f"Consent definition {cdef_id} is not active for date {today}."
            )
        accepted = bool(item.get("accepted"))
        pic, _ = PatientIntakeConsent.objects.get_or_create(
            intake_form_id=intake_form.id,
            consent_definition_id=cdef_id,
            defaults={"accepted": False, "accepted_at": None},
        )
        pic.accepted = accepted
        pic.accepted_at = now if accepted else None
        pic.save(update_fields=["accepted", "accepted_at"])

    return intake_form


# Max signature file size (bytes), e.g. 2MB
SIGNATURE_MAX_SIZE = 2 * 1024 * 1024


@transaction.atomic
def save_intake_signature(
    *,
    intake_form_id: uuid.UUID,
    signature_base64: str,
) -> PatientIntakeForm:
    """
    Decode base64 signature, store file under MEDIA_ROOT/signatures/YYYY/MM/<uuid>.png,
    set signature_file_path and signature_sha256 on the intake form.
    Raises InvalidSignatureError if payload is invalid or too large.
    Raises StateTransitionError if form is not IN_PROGRESS.
    """
    import base64
    import hashlib
    from pathlib import Path

    from django.conf import settings

    intake_form = PatientIntakeForm.objects.select_for_update().get(id=intake_form_id)
    if intake_form.form_status != IntakeStatus.IN_PROGRESS:
        raise StateTransitionError("Signature can be set only for IN_PROGRESS intake form.")

    # Strip data URL prefix if present
    data = signature_base64
    if "," in data:
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=True)
    except Exception:
        raise InvalidSignatureError("Invalid base64 in signature payload.")
    if len(raw) == 0:
        raise InvalidSignatureError("Signature payload is empty.")
    if len(raw) > SIGNATURE_MAX_SIZE:
        raise InvalidSignatureError(f"Signature payload exceeds max size ({SIGNATURE_MAX_SIZE} bytes).")

    sha256_hash = hashlib.sha256(raw).hexdigest()
    now = timezone.now()
    year_month = now.strftime("%Y/%m")
    rel_dir = Path("signatures") / year_month
    dir_path = Path(settings.MEDIA_ROOT) / rel_dir
    dir_path.mkdir(parents=True, exist_ok=True)
    file_name = f"{intake_form_id}.png"
    file_path = dir_path / file_name
    file_path.write_bytes(raw)
    # Store path relative to MEDIA_ROOT for portability
    relative_path = str(rel_dir / file_name)

    intake_form.signature_file_path = relative_path
    intake_form.signature_sha256 = sha256_hash
    intake_form.save(update_fields=["signature_file_path", "signature_sha256", "updated_at"])
    return intake_form


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
