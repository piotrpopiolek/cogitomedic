from __future__ import annotations

import base64
import hashlib
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.core.exceptions import DomainError, StateTransitionError
from apps.intake.models import (
    AnamnesisOptionDefinition,
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    IntakeOutboxEventType,
    IntakeOutboxStatus,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.operations.services import create_audit_event
from apps.reception.models import QueueEntry, QueueEntryStatus

logger = logging.getLogger(__name__)


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


def _humanize_code(code: str) -> str:
    mapping = {
        "YES": "Yes",
        "NO": "No",
        "UNKNOWN": "Unknown",
    }
    if code in mapping:
        return mapping[code]
    return code.replace("_", " ").title()


def _localized_text(*, value_de: str, value_en: str, value_pl: str, locale: str) -> str:
    if locale.startswith("pl"):
        return (value_pl or "").strip() or value_de
    if locale.startswith("en"):
        return (value_en or "").strip() or value_de
    return value_de


def _read_signature_data_url(intake_form: PatientIntakeForm) -> str:
    if not intake_form.signature_file_path:
        raise InvalidSignatureError("Signature path is missing.")
    file_path = Path(intake_form.signature_file_path)
    if not file_path.is_absolute():
        file_path = Path(settings.MEDIA_ROOT) / file_path
    if not file_path.exists() or not file_path.is_file():
        raise InvalidSignatureError("Signature file does not exist.")
    raw = file_path.read_bytes()
    if not raw:
        raise InvalidSignatureError("Signature file is empty.")
    checksum = hashlib.sha256(raw).hexdigest()
    if (intake_form.signature_sha256 or "") and intake_form.signature_sha256 != checksum:
        raise InvalidSignatureError("Signature checksum mismatch.")
    encoded = base64.b64encode(raw).decode("ascii")
    suffix = file_path.suffix.lower()
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{encoded}"


def _build_intake_snapshot_payload(*, intake_form: PatientIntakeForm, now: datetime) -> dict[str, Any]:
    session = intake_form.session
    queue_entry = intake_form.queue_entry
    patient = queue_entry.patient
    locale = (session.form_locale or "de-DE")[:10]

    consents = []
    consent_rows = (
        PatientIntakeConsent.objects.filter(intake_form_id=intake_form.id)
        .select_related("consent_definition")
        .order_by("consent_definition__display_order", "consent_definition__code")
    )
    for consent in consent_rows:
        definition = consent.consent_definition
        consents.append(
            {
                "consent_definition_id": str(definition.id),
                "code": definition.code,
                "version": definition.version,
                "is_required": definition.is_required,
                "accepted": consent.accepted,
                "accepted_at": consent.accepted_at.isoformat() if consent.accepted_at else None,
                "title_de": definition.title_de,
                "title_locale": _localized_text(
                    value_de=definition.title_de,
                    value_en=definition.title_en,
                    value_pl=definition.title_pl,
                    locale=locale,
                ),
                "content_de": definition.content_de,
                "content_locale": _localized_text(
                    value_de=definition.content_de,
                    value_en=definition.content_en,
                    value_pl=definition.content_pl,
                    locale=locale,
                ),
            }
        )

    answers_raw = intake_form.anamnesis_payload.get("answers") or []
    question_codes = [
        answer.get("question_code")
        for answer in answers_raw
        if isinstance(answer, dict) and isinstance(answer.get("question_code"), str)
    ]
    active_options_prefetch = Prefetch(
        "options",
        queryset=AnamnesisOptionDefinition.objects.filter(is_active=True).order_by("display_order", "code")
    )
    questions = (
        AnamnesisQuestionDefinition.objects.filter(_effective_question_filter(now.date()), code__in=question_codes)
        .prefetch_related(active_options_prefetch)
        .order_by("-version")
    )
    question_by_code = {q.code: q for q in questions}
    anamnesis_answers = []
    for answer in answers_raw:
        if not isinstance(answer, dict):
            continue
        question_code = answer.get("question_code")
        if not question_code:
            continue
        question = question_by_code.get(question_code)
        selected_option_codes = set(answer.get("selected_option_codes") or [])
        selected_options = []
        all_options = []
        if question:
            for opt in question.options.all():
                label_locale = _localized_text(
                    value_de=opt.option_text_de,
                    value_en=opt.option_text_en,
                    value_pl=opt.option_text_pl,
                    locale=locale,
                )
                all_options.append(
                    {
                        "option_code": opt.code,
                        "label_de": opt.option_text_de,
                        "label_locale": label_locale,
                        "selected": opt.code in selected_option_codes,
                    }
                )
            options_by_code = {opt.code: opt for opt in question.options.all()}
            for option_code in selected_option_codes:
                opt = options_by_code.get(option_code)
                if opt:
                    selected_options.append(
                        {
                            "option_code": opt.code,
                            "label_de": opt.option_text_de,
                            "label_locale": _localized_text(
                                value_de=opt.option_text_de,
                                value_en=opt.option_text_en,
                                value_pl=opt.option_text_pl,
                                locale=locale,
                            ),
                        }
                    )
                else:
                    fallback = _humanize_code(option_code)
                    selected_options.append(
                        {
                            "option_code": option_code,
                            "label_de": fallback,
                            "label_locale": fallback,
                        }
                    )
                    if not any(o["option_code"] == option_code for o in all_options):
                        all_options.append(
                            {
                                "option_code": option_code,
                                "label_de": fallback,
                                "label_locale": fallback,
                                "selected": True,
                            }
                        )
        else:
            for option_code in selected_option_codes:
                fallback = _humanize_code(option_code)
                selected_options.append(
                    {"option_code": option_code, "label_de": fallback, "label_locale": fallback}
                )
                all_options.append(
                    {
                        "option_code": option_code,
                        "label_de": fallback,
                        "label_locale": fallback,
                        "selected": True,
                    }
                )
        question_text_de = question.question_text_de if question else _humanize_code(question_code)
        question_text_locale = (
            _localized_text(
                value_de=question.question_text_de,
                value_en=question.question_text_en,
                value_pl=question.question_text_pl,
                locale=locale,
            )
            if question
            else _humanize_code(question_code)
        )
        anamnesis_answers.append(
            {
                "question_code": question_code,
                "question_text_de": question_text_de,
                "question_text_locale": question_text_locale,
                "selected_options": selected_options,
                "all_options": all_options,
                "free_text": answer.get("free_text"),
            }
        )

    return {
        "schema_version": 1,
        "captured_at": now.isoformat(),
        "base_locale": "de-DE",
        "form_locale": locale,
        "intake_form_id": str(intake_form.id),
        "queue_entry_id": str(queue_entry.id),
        "patient": {
            "id": str(patient.id),
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth.isoformat(),
            "phone": patient.phone,
            "email": patient.email,
        },
        "consents": consents,
        "anamnesis": {
            "schema_version": intake_form.anamnesis_schema_version,
            "answers": anamnesis_answers,
        },
        "signature": {
            "data_url": _read_signature_data_url(intake_form),
            "sha256": intake_form.signature_sha256 or "",
            "file_path": intake_form.signature_file_path,
        },
        "submitted_at": now.isoformat(),
    }


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
        .values("id", "code", "title_de", "title_en", "title_pl", "content_de", "content_en", "content_pl", "is_required")
    )
    consent_by_def_id = {
        c.consent_definition_id: c
        for c in PatientIntakeConsent.objects.filter(intake_form_id=intake_form.id).select_related(
            "consent_definition"
        )
    }
    use_en = form_locale.startswith("en")
    use_pl = form_locale.startswith("pl")
    consents_payload = []
    for cd in consent_defs:
        cd_id = cd["id"]
        pic = consent_by_def_id.get(cd_id)
        if use_en and (cd.get("title_en") or "").strip():
            title = cd["title_en"]
            content = (cd.get("content_en") or "").strip() or (cd["content_de"] or "")
        elif use_pl and (cd.get("title_pl") or "").strip():
            title = cd["title_pl"]
            content = (cd.get("content_pl") or "").strip() or (cd["content_de"] or "")
        else:
            title = cd["title_de"]
            content = (cd["content_de"] or "")
        consents_payload.append({
            "consent_definition_id": str(cd_id),
            "code": cd["code"],
            "title": title,
            "content": content,
            "is_required": cd["is_required"],
            "accepted": pic.accepted if pic else False,
            "accepted_at": pic.accepted_at.isoformat() if pic and pic.accepted_at else None,
        })

    active_options_prefetch = Prefetch(
        "options",
        queryset=AnamnesisOptionDefinition.objects.filter(is_active=True).order_by("display_order", "code")
    )
    # Anamnesis questions effective today with options; attach current answer from payload
    question_defs = (
        AnamnesisQuestionDefinition.objects.filter(_effective_question_filter(today))
        .prefetch_related(active_options_prefetch)
        .order_by("display_order", "code")
    )
    answers_raw = intake_form.anamnesis_payload.get("answers") or []
    answer_by_code = {a.get("question_code"): a for a in answers_raw if isinstance(a, dict) and a.get("question_code")}

    def option_label(opt: AnamnesisOptionDefinition) -> str:
        if form_locale.startswith("de"):
            return opt.option_text_de
        if form_locale.startswith("pl") and (opt.option_text_pl or "").strip():
            return opt.option_text_pl
        return opt.option_text_en

    def question_text(q: AnamnesisQuestionDefinition) -> str:
        if form_locale.startswith("de"):
            return q.question_text_de
        if form_locale.startswith("pl") and (q.question_text_pl or "").strip():
            return q.question_text_pl
        return q.question_text_en

    anamnesis_questions_payload = []
    for q in question_defs:
        if not q.is_active:
            continue
        options = [{"option_code": o.code, "label": option_label(o)} for o in q.options.all()]
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
def save_intake_body_map(
    *,
    intake_form_id: uuid.UUID,
    body_map_schema_version: int,
    body_map_data: list[dict],
) -> PatientIntakeForm:
    """
    Update body map data for an in-progress intake form.

    body_map_data: list of {x, y, side, label?} with x,y in [0,1], side in ('front','back').
    """
    intake_form = PatientIntakeForm.objects.select_for_update().get(id=intake_form_id)
    if intake_form.form_status != IntakeStatus.IN_PROGRESS:
        raise StateTransitionError("Body map can be edited only for IN_PROGRESS intake form.")
    raw = []
    for p in body_map_data:
        pt = {"x": float(p["x"]), "y": float(p["y"]), "side": str(p["side"])}
        if p.get("label"):
            pt["label"] = str(p["label"])
        raw.append(pt)
    intake_form.body_map_schema_version = body_map_schema_version
    intake_form.body_map_data = raw
    intake_form.save(update_fields=["body_map_schema_version", "body_map_data", "updated_at"])
    return intake_form


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
    intake_form = PatientIntakeForm.objects.select_for_update().get(id=intake_form_id)
    if intake_form.form_status != IntakeStatus.IN_PROGRESS:
        raise StateTransitionError("Signature can be set only for IN_PROGRESS intake form.")

    # Strip data URL prefix if present
    data = signature_base64
    if "," in data:
        data = data.split(",", 1)[1]
        
    if len(data) > SIGNATURE_MAX_SIZE * 1.4:
        raise InvalidSignatureError(f"Signature payload exceeds max size before decoding.")
        
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
    rel_dir = Path(getattr(settings, "SIGNATURES_RELATIVE_DIR", "signatures")) / year_month
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
        PatientIntakeForm.objects.select_related("session", "queue_entry", "queue_entry__patient")
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

    today = now.date()
    required_consent_ids = set(
        ConsentDefinition.objects.filter(
            _effective_consent_filter(today), is_required=True
        ).values_list("id", flat=True)
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
            _effective_question_filter(today), is_required=True
        ).values_list("code", flat=True)
    )
    answered_question_codes = _extract_answered_question_codes(intake_form.anamnesis_payload)
    missing_question_codes = required_question_codes - answered_question_codes
    if missing_question_codes:
        raise RequiredAnamnesisMissingError("Required active anamnesis questions are not answered.")

    # Optimistic lock style transition: only one concurrent submit wins.
    updated_rows = PatientIntakeForm.objects.filter(
        id=intake_form.id,
        form_status=IntakeStatus.IN_PROGRESS,
    ).update(
        form_status=IntakeStatus.SUBMITTED,
        submitted_at=now,
        updated_at=now,
    )
    if updated_rows == 0:
        refreshed = PatientIntakeForm.objects.get(id=intake_form.id)
        if refreshed.form_status == IntakeStatus.SUBMITTED:
            return refreshed
        raise StateTransitionError("Only IN_PROGRESS intake form can be submitted.")

    snapshot_payload = _build_intake_snapshot_payload(intake_form=intake_form, now=now)
    latest_version_no = (
        IntakeDocumentVersion.objects.filter(intake_form_id=intake_form.id)
        .order_by("-version_no")
        .values_list("version_no", flat=True)
        .first()
        or 0
    )
    intake_version = IntakeDocumentVersion.objects.create(
        intake_form_id=intake_form.id,
        version_no=latest_version_no + 1,
        form_locale=(session.form_locale or "de-DE")[:10],
        snapshot_payload=snapshot_payload,
    )
    IntakeOutboxEvent.objects.get_or_create(
        intake_document_version=intake_version,
        event_type=IntakeOutboxEventType.GENERATE_INTAKE_PDF,
        defaults={
            "aggregate_id": intake_version.id,
            "payload_schema_version": 1,
            "payload": {
                "intake_form_id": str(intake_form.id),
                "intake_document_version_id": str(intake_version.id),
            },
            "status": IntakeOutboxStatus.PENDING,
        },
    )

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
            "intake_document_version_id": str(intake_version.id),
            "queue_entry_id": str(queue_entry.id),
            "session_id": str(session.id),
        },
    )
    logger.info(
        "intake_submitted",
        extra={
            "intake_form_id": str(intake_form.id),
            "intake_document_version_id": str(intake_version.id),
            "queue_entry_id": str(queue_entry.id),
            "patient_id": str(queue_entry.patient_id),
            "submitted_by_user_id": str(submitted_by_user_id) if submitted_by_user_id else None,
        },
    )

    return PatientIntakeForm.objects.get(id=intake_form.id)


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
