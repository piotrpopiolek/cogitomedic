from __future__ import annotations

import base64
import hashlib
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError, StateTransitionError
from apps.core.translation_service import get_form_ui_strings
from apps.intake.constants import SIGNATURE_MAX_SIZE
from apps.intake.form_access import (
    assert_intake_form_clinic_scope,
    intake_allows_patient_edits,
)
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
from apps.reception.process_types import PROCESS_TYPE_TELEDERM, coerce_process_type
from apps.reception.services import (
    issue_tablet_session_latest_wins,
    raise_if_queue_entry_cancelled,
)

logger = logging.getLogger(__name__)

CONTACT_METHOD_CONSENT_CODE = "PRAEVENTIONS_ERINNERUNGEN_KONTAKTWEG"
CONTACT_METHOD_ALLOWED_OPTIONS = {"EMAIL", "SMS", "PHONE"}


def _format_patient_dob_for_form(dob: date | None, form_locale: str) -> str:
    """Locale-aware DOB label for tablet verification card."""
    if dob is None:
        return ""
    if form_locale.startswith("en"):
        return dob.strftime("%d %B %Y")
    return dob.strftime("%d.%m.%Y")


# Melanoma intake: if NEW_SKIN_CHANGES_LOCATION is answered affirmatively, the PDF includes the body map.
NEW_SKIN_CHANGES_LOCATION = "Q4_NEW_SKIN_CHANGES_LOCATION"
NEW_SKIN_CHANGES_AFFIRMATIVE_CODES = frozenset({"YES", "TRUE"})


def _body_map_coordinate_float(value: object) -> float | None:
    """Parse JSON body-map x/y; rejects bool (subclass of int)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _patient_intake_consent_selected_codes(consent: PatientIntakeConsent) -> list[str]:
    raw = (
        consent.selected_option_codes
        if isinstance(consent.selected_option_codes, list)
        else []
    )
    out = [str(x).strip().upper() for x in raw if str(x).strip()]
    if not out and (consent.selected_option_code or "").strip():
        out = [(consent.selected_option_code or "").strip().upper()]
    return out


def _contact_method_pdf_options(
    *, locale: str, selected_codes: Iterable[str]
) -> list[dict[str, Any]]:
    """Rows for intake PDF (same shape as anamnesis ``all_options`` items)."""
    selected = {c for c in selected_codes if c in CONTACT_METHOD_ALLOWED_OPTIONS}
    loc = (locale or "de-DE").lower()
    use_en = loc.startswith("en")
    use_pl = loc.startswith("pl")
    ui = get_form_ui_strings(locale)
    phone_de = "Telefon"
    phone_loc = ui.get("contact_method_phone", phone_de) if ui else phone_de
    email_de = "E-Mail"
    email_loc = "E-mail" if use_pl else ("Email" if use_en else email_de)
    rows: list[dict[str, Any]] = []
    for code, label_de, label_loc in (
        ("EMAIL", email_de, email_loc),
        ("SMS", "SMS", "SMS"),
        ("PHONE", phone_de, phone_loc),
    ):
        rows.append(
            {
                "option_code": code,
                "label_de": label_de,
                "label_locale": label_loc,
                "selected": code in selected,
            }
        )
    return rows


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
        raise InvalidSignatureError(
            domain_message("other.domain.intake_signature_path_missing"),
            api_message_key="other.domain.intake_signature_path_missing",
        )
    file_path = Path(intake_form.signature_file_path)
    if not file_path.is_absolute():
        file_path = Path(settings.MEDIA_ROOT) / file_path
    if not file_path.exists() or not file_path.is_file():
        raise InvalidSignatureError(
            domain_message("other.domain.intake_signature_file_missing"),
            api_message_key="other.domain.intake_signature_file_missing",
        )
    raw = file_path.read_bytes()
    if not raw:
        raise InvalidSignatureError(
            domain_message("other.domain.intake_signature_file_empty"),
            api_message_key="other.domain.intake_signature_file_empty",
        )
    if len(raw) > SIGNATURE_MAX_SIZE:
        raise InvalidSignatureError(
            domain_message(
                "other.domain.signature_payload_too_large", max_bytes=SIGNATURE_MAX_SIZE
            ),
            api_message_key="other.domain.signature_payload_too_large",
            api_message_params={"max_bytes": SIGNATURE_MAX_SIZE},
        )
    checksum = hashlib.sha256(raw).hexdigest()
    if (
        intake_form.signature_sha256 or ""
    ) and intake_form.signature_sha256 != checksum:
        raise InvalidSignatureError(
            domain_message("other.domain.intake_signature_checksum_mismatch"),
            api_message_key="other.domain.intake_signature_checksum_mismatch",
        )
    suffix = file_path.suffix.lower()
    is_png = raw.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = raw.startswith(b"\xff\xd8\xff")
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise InvalidSignatureError(
            domain_message("other.domain.signature_image_format_invalid"),
            api_message_key="other.domain.signature_image_format_invalid",
        )
    if suffix == ".png" and not is_png:
        raise InvalidSignatureError(
            domain_message("other.domain.signature_image_format_invalid"),
            api_message_key="other.domain.signature_image_format_invalid",
        )
    if suffix in {".jpg", ".jpeg"} and not is_jpeg:
        raise InvalidSignatureError(
            domain_message("other.domain.signature_image_format_invalid"),
            api_message_key="other.domain.signature_image_format_invalid",
        )
    encoded = base64.b64encode(raw).decode("ascii")
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{encoded}"


def _anamnesis_selected_affirmative(
    intake_form: PatientIntakeForm, *, question_code: str, affirmative: frozenset[str]
) -> bool:
    """True if the given question has at least one selected option in *affirmative*."""
    target = question_code.strip()
    if not target:
        return False
    payload = intake_form.anamnesis_payload or {}
    for answer in payload.get("answers") or []:
        if not isinstance(answer, dict):
            continue
        raw_qc = answer.get("question_code")
        if not isinstance(raw_qc, str):
            continue
        if raw_qc.strip() != target:
            continue
        raw = answer.get("selected_option_codes") or []
        if not isinstance(raw, list):
            return False
        selected = {str(c).strip().upper() for c in raw if str(c).strip()}
        return bool(selected & affirmative)
    return False


def _body_map_points_for_intake_pdf(body_map_data: Any) -> list[dict[str, Any]]:
    """Normalize ``body_map_data`` JSON to marker dicts for the intake PDF template."""
    if not isinstance(body_map_data, list):
        return []
    out: list[dict[str, Any]] = []
    for i, p in enumerate(body_map_data):
        if not isinstance(p, dict):
            continue
        x = _body_map_coordinate_float(p.get("x"))
        y = _body_map_coordinate_float(p.get("y"))
        if x is None or y is None:
            continue
        side = str(p.get("side") or "").strip()
        out.append(
            {
                "left_pct": f"{x * 100.0:.4f}",
                "top_pct": f"{y * 100.0:.4f}",
                "side": side,
                "index": i + 1,
            }
        )
    return out


def _intake_pdf_body_map_section(
    intake_form: PatientIntakeForm,
) -> dict[str, Any] | None:
    """Body map block for the intake PDF when NEW_SKIN_CHANGES_LOCATION is answered affirmatively."""
    if not _anamnesis_selected_affirmative(
        intake_form,
        question_code=NEW_SKIN_CHANGES_LOCATION,
        affirmative=NEW_SKIN_CHANGES_AFFIRMATIVE_CODES,
    ):
        return None
    return {
        "image_rel_path": "static/tablet/body.jpg",
        "points": _body_map_points_for_intake_pdf(intake_form.body_map_data),
    }


def _build_intake_snapshot_payload(
    *, intake_form: PatientIntakeForm, now: datetime
) -> dict[str, Any]:
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
        selected_codes = _patient_intake_consent_selected_codes(consent)
        row: dict[str, Any] = {
            "consent_definition_id": str(definition.id),
            "code": definition.code,
            "version": definition.version,
            "is_required": definition.is_required,
            "accepted": consent.accepted,
            "accepted_at": (
                consent.accepted_at.isoformat() if consent.accepted_at else None
            ),
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
            "selected_option_codes": selected_codes,
        }
        if definition.code == CONTACT_METHOD_CONSENT_CODE:
            row["contact_method_all_options"] = _contact_method_pdf_options(
                locale=locale, selected_codes=selected_codes
            )
        consents.append(row)

    answers_raw = intake_form.anamnesis_payload.get("answers") or []
    question_codes_set: set[str] = set()
    for answer in answers_raw:
        if not isinstance(answer, dict):
            continue
        raw_code = answer.get("question_code")
        if not isinstance(raw_code, str):
            continue
        qc = raw_code.strip()
        if qc:
            question_codes_set.add(qc)
    question_codes = list(question_codes_set)
    active_options_prefetch = Prefetch(
        "options",
        queryset=AnamnesisOptionDefinition.objects.filter(is_active=True).order_by(
            "display_order", "code"
        ),
    )
    questions = (
        AnamnesisQuestionDefinition.objects.filter(
            _effective_question_filter(
                timezone.localdate(now),
                coerce_process_type(intake_form.queue_entry.process_type),
            ),
            code__in=question_codes,
        )
        .distinct()
        .prefetch_related(active_options_prefetch)
        .order_by("-version")
    )
    question_by_code = {q.code: q for q in questions}
    body_map_section = _intake_pdf_body_map_section(intake_form)
    anamnesis_answers: list[dict[str, Any]] = []
    for answer in answers_raw:
        if not isinstance(answer, dict):
            continue
        raw_qc = answer.get("question_code")
        if not isinstance(raw_qc, str):
            continue
        question_code = raw_qc.strip()
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
                    {
                        "option_code": option_code,
                        "label_de": fallback,
                        "label_locale": fallback,
                    }
                )
                all_options.append(
                    {
                        "option_code": option_code,
                        "label_de": fallback,
                        "label_locale": fallback,
                        "selected": True,
                    }
                )
        question_text_de = (
            question.question_text_de if question else _humanize_code(question_code)
        )
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
        answer_row: dict[str, Any] = {
            "question_code": question_code,
            "question_text_de": question_text_de,
            "question_text_locale": question_text_locale,
            "selected_options": selected_options,
            "all_options": all_options,
            "free_text": answer.get("free_text"),
        }
        if body_map_section is not None and question_code == NEW_SKIN_CHANGES_LOCATION:
            answer_row["body_map"] = body_map_section
        anamnesis_answers.append(answer_row)

    anamnesis_answers.sort(
        key=lambda r: (
            (
                question_by_code[r["question_code"]].display_order,
                question_by_code[r["question_code"]].code,
            )
            if r.get("question_code") in question_by_code
            else (9999, r.get("question_code") or "")
        )
    )

    snapshot: dict[str, Any] = {
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
        "body_map": body_map_section,
    }
    if (
        coerce_process_type(queue_entry.process_type) == PROCESS_TYPE_TELEDERM
        and intake_form.telederm_payload
    ):
        snapshot["telederm"] = intake_form.telederm_payload
    return snapshot


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

        has_selected_options = (
            isinstance(selected_option_codes, list) and len(selected_option_codes) > 0
        )
        has_free_text = isinstance(free_text, str) and bool(free_text.strip())
        if has_selected_options or has_free_text:
            answered_codes.add(question_code)

    return answered_codes


def _effective_consent_filter(today: date, process_type: str):
    return (
        Q(is_active=True)
        & Q(effective_from__lte=today)
        & (Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        & Q(process_links__process_type=process_type)
    )


def _effective_question_filter(today: date, process_type: str):
    return (
        Q(is_active=True)
        & Q(effective_from__lte=today)
        & (Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        & Q(process_links__process_type=process_type)
    )


def get_intake_form_context(
    *,
    intake_form_id: uuid.UUID,
    form_locale: str = "de-DE",
    tablet_restrict_to_today: bool = False,
    allowed_clinic_site_ids: Iterable[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """
    Build intake form context for tablet/verification screen.

    Returns patient (read-only), consents with accepted state, anamnesis questions
    with options and current answer, body_map and form status.
    Raises ObjectDoesNotExist if form not found.
    For tablet_restrict_to_today=True (TABLET role), returns 404 when queue is not today.
    """
    today = timezone.localdate()
    intake_form = PatientIntakeForm.objects.select_related(
        "session",
        "queue_entry",
        "queue_entry__patient",
        "queue_entry__daily_queue",
    ).get(id=intake_form_id)
    assert_intake_form_clinic_scope(
        intake_form=intake_form,
        allowed_clinic_site_ids=allowed_clinic_site_ids,
    )
    if (
        tablet_restrict_to_today
        and intake_form.queue_entry.daily_queue.queue_date != today
    ):
        raise ObjectDoesNotExist("Intake form queue is not from today.")
    session = intake_form.session
    queue_entry = intake_form.queue_entry
    patient = queue_entry.patient
    process_type = coerce_process_type(queue_entry.process_type)

    # Consent definitions effective today for this process; then merge with choices
    consent_defs = (
        ConsentDefinition.objects.filter(_effective_consent_filter(today, process_type))
        .distinct()
        .order_by("display_order", "code")
        .values(
            "id",
            "code",
            "title_de",
            "title_en",
            "title_pl",
            "content_de",
            "content_en",
            "content_pl",
            "is_required",
        )
    )
    consent_by_def_id = {
        c.consent_definition_id: c
        for c in PatientIntakeConsent.objects.filter(
            intake_form_id=intake_form.id
        ).select_related("consent_definition")
    }
    use_en = form_locale.startswith("en")
    use_pl = form_locale.startswith("pl")
    consents_payload = []
    ui = get_form_ui_strings(form_locale)

    for cd in consent_defs:
        cd_id = cd["id"]
        pic = consent_by_def_id.get(cd_id)
        selected_option_codes = []
        if pic:
            raw_codes = (
                pic.selected_option_codes
                if isinstance(pic.selected_option_codes, list)
                else []
            )
            selected_option_codes = [
                str(x).strip().upper() for x in raw_codes if str(x).strip()
            ]
            if not selected_option_codes and (pic.selected_option_code or "").strip():
                selected_option_codes = [
                    (pic.selected_option_code or "").strip().upper()
                ]
        if use_en and (cd.get("title_en") or "").strip():
            title = cd["title_en"]
            content = (cd.get("content_en") or "").strip() or (cd["content_de"] or "")
        elif use_pl and (cd.get("title_pl") or "").strip():
            title = cd["title_pl"]
            content = (cd.get("content_pl") or "").strip() or (cd["content_de"] or "")
        else:
            title = cd["title_de"]
            content = cd["content_de"] or ""

        options = []
        confirm_label = ""
        is_multi = False

        if cd["code"] == CONTACT_METHOD_CONSENT_CODE:
            is_multi = True
            options = [
                {"code": "EMAIL", "label": "E-Mail"},
                {"code": "SMS", "label": "SMS"},
                {"code": "PHONE", "label": ui.get("contact_method_phone", "Telefon")},
            ]
        if cd["code"] == "DS_EINWILLIGUNG_ERGEBNISSES":
            confirm_label = ui.get("consent_result_portal_agree") or ""
        if cd["code"] == "PRAEVENTIONS_ERINNERUNGEN_EINWILLIGUNG":
            confirm_label = ui.get("consent_contact_agree") or ""

        consents_payload.append(
            {
                "consent_definition_id": str(cd_id),
                "code": cd["code"],
                "title": title,
                "content": content,
                "is_required": cd["is_required"],
                "accepted": pic.accepted if pic else False,
                "accepted_at": (
                    pic.accepted_at.isoformat() if pic and pic.accepted_at else None
                ),
                "selected_option_codes": selected_option_codes,
                "selected_option_code": (
                    selected_option_codes[0] if selected_option_codes else ""
                ),
                "is_multi": is_multi,
                "options": options,
                "confirm_label": confirm_label,
            }
        )

    active_options_prefetch = Prefetch(
        "options",
        queryset=AnamnesisOptionDefinition.objects.filter(is_active=True).order_by(
            "display_order", "code"
        ),
    )
    # Anamnesis questions effective today with options; attach current answer from payload
    question_defs = (
        AnamnesisQuestionDefinition.objects.filter(
            _effective_question_filter(today, process_type)
        )
        .distinct()
        .prefetch_related(active_options_prefetch)
        .order_by("display_order", "code")
    )
    answers_raw = intake_form.anamnesis_payload.get("answers") or []
    answer_by_code = {
        a.get("question_code"): a
        for a in answers_raw
        if isinstance(a, dict) and a.get("question_code")
    }

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
        options = [
            {"option_code": o.code, "label": option_label(o)} for o in q.options.all()
        ]
        current = answer_by_code.get(q.code) or {}
        answer = {
            "selected_option_codes": current.get("selected_option_codes") or [],
            "free_text": current.get("free_text"),
        }
        anamnesis_questions_payload.append(
            {
                "question_code": q.code,
                "question_text": question_text(q),
                "answer_type": q.answer_type,
                "is_required": q.is_required,
                "options": options,
                "answer": answer,
            }
        )

    # Patient (read-only for verification)
    patient_payload = {
        "id": str(patient.id),
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": (
            patient.date_of_birth.isoformat() if patient.date_of_birth else ""
        ),
        "date_of_birth_display": _format_patient_dob_for_form(
            patient.date_of_birth, form_locale
        ),
        "phone": patient.phone,
        "email": patient.email,
    }

    context: dict[str, Any] = {
        "intake_form_id": str(intake_form.id),
        "queue_entry_id": str(queue_entry.id),
        "process_type": process_type,
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
    if process_type == PROCESS_TYPE_TELEDERM:
        from apps.telederm.services import load_catalog, serialize_catalog_for_tablet

        catalog = load_catalog()
        payload = intake_form.telederm_payload or {}
        context["telederm"] = serialize_catalog_for_tablet(
            catalog=catalog, payload=payload, locale=form_locale
        )
        context["telederm_schema_version"] = intake_form.telederm_schema_version or 1
    return context


@transaction.atomic
def save_intake_body_map(
    *,
    intake_form_id: uuid.UUID,
    body_map_schema_version: int,
    body_map_data: list[dict],
    allowed_clinic_site_ids: Iterable[uuid.UUID] | None = None,
) -> PatientIntakeForm:
    """
    Update body map data for an in-progress intake form.

    body_map_data: list of {x, y, side, label?} with x,y in [0,1], side in ('front','back').
    """
    intake_form = (
        PatientIntakeForm.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=intake_form_id)
    )
    assert_intake_form_clinic_scope(
        intake_form=intake_form,
        allowed_clinic_site_ids=allowed_clinic_site_ids,
    )
    if not intake_allows_patient_edits(intake_form.form_status):
        raise StateTransitionError(
            domain_message("other.domain.intake_body_map_in_progress_only"),
            api_message_key="other.domain.intake_body_map_in_progress_only",
        )
    raw = []
    for p in body_map_data:
        pt = {"x": float(p["x"]), "y": float(p["y"]), "side": str(p["side"])}
        if p.get("label"):
            pt["label"] = str(p["label"])
        raw.append(pt)
    intake_form.body_map_schema_version = body_map_schema_version
    intake_form.body_map_data = raw
    intake_form.save(
        update_fields=["body_map_schema_version", "body_map_data", "updated_at"]
    )
    return intake_form


@transaction.atomic
def save_intake_consents(
    *,
    intake_form_id: uuid.UUID,
    consents_payload: list[dict],
    allowed_clinic_site_ids: Iterable[uuid.UUID] | None = None,
) -> PatientIntakeForm:
    """
    Replace consent acceptance set for an in-progress intake form.

    Each item: consent_definition_id (UUID), accepted (bool).
    Raises ConsentNotActiveError if any consent definition is not active for today.
    """
    today = timezone.localdate()
    now = timezone.now()

    intake_form = (
        PatientIntakeForm.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=intake_form_id)
    )
    process_type = coerce_process_type(intake_form.queue_entry.process_type)
    effective_defs = list(
        ConsentDefinition.objects.filter(_effective_consent_filter(today, process_type))
        .distinct()
        .values("id", "code")
    )
    effective_ids = {row["id"] for row in effective_defs}
    consent_code_by_id = {row["id"]: row["code"] for row in effective_defs}
    assert_intake_form_clinic_scope(
        intake_form=intake_form,
        allowed_clinic_site_ids=allowed_clinic_site_ids,
    )
    if not intake_allows_patient_edits(intake_form.form_status):
        raise StateTransitionError(
            domain_message("other.domain.intake_consents_in_progress_only"),
            api_message_key="other.domain.intake_consents_in_progress_only",
        )

    for item in consents_payload:
        cdef_id = item.get("consent_definition_id")
        if cdef_id not in effective_ids:
            cid = str(cdef_id)
            d = str(today)
            raise ConsentNotActiveError(
                domain_message(
                    "other.domain.consent_definition_not_active", consent_id=cid, date=d
                ),
                api_message_key="other.domain.consent_definition_not_active",
                api_message_params={"consent_id": cid, "date": d},
            )
        accepted = bool(item.get("accepted"))
        consent_code = consent_code_by_id.get(cdef_id)
        raw_codes = item.get("selected_option_codes")
        selected_option_codes = []
        if isinstance(raw_codes, list):
            for raw in raw_codes:
                val = str(raw).strip().upper()
                if val and val not in selected_option_codes:
                    selected_option_codes.append(val)
        fallback_one = str(item.get("selected_option_code") or "").strip().upper()
        if fallback_one and fallback_one not in selected_option_codes:
            selected_option_codes.append(fallback_one)
        if consent_code == CONTACT_METHOD_CONSENT_CODE and accepted:
            if not selected_option_codes:
                raise DomainError(
                    domain_message("other.domain.intake_contact_method_required"),
                    api_message_key="other.domain.intake_contact_method_required",
                )
            invalid = [
                x
                for x in selected_option_codes
                if x not in CONTACT_METHOD_ALLOWED_OPTIONS
            ]
            if invalid:
                raise DomainError(
                    domain_message("other.domain.intake_contact_method_invalid"),
                    api_message_key="other.domain.intake_contact_method_invalid",
                )
        else:
            selected_option_codes = []
        pic, _ = PatientIntakeConsent.objects.get_or_create(
            intake_form_id=intake_form.id,
            consent_definition_id=cdef_id,
            defaults={
                "accepted": False,
                "accepted_at": None,
                "selected_option_code": "",
                "selected_option_codes": [],
            },
        )
        pic.accepted = accepted
        pic.accepted_at = now if accepted else None
        pic.selected_option_codes = selected_option_codes
        pic.selected_option_code = (
            selected_option_codes[0] if selected_option_codes else ""
        )
        pic.save(
            update_fields=[
                "accepted",
                "accepted_at",
                "selected_option_code",
                "selected_option_codes",
            ]
        )

    return intake_form


@transaction.atomic
def save_intake_signature(
    *,
    intake_form_id: uuid.UUID,
    signature_base64: str,
    allowed_clinic_site_ids: Iterable[uuid.UUID] | None = None,
) -> PatientIntakeForm:
    """
    Decode base64 signature, store file under MEDIA_ROOT/signatures/YYYY/MM/<uuid>.png,
    set signature_file_path and signature_sha256 on the intake form.
    Raises InvalidSignatureError if payload is invalid or too large.
    Raises StateTransitionError if form is not editable.
    """
    intake_form = (
        PatientIntakeForm.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=intake_form_id)
    )
    assert_intake_form_clinic_scope(
        intake_form=intake_form,
        allowed_clinic_site_ids=allowed_clinic_site_ids,
    )
    if not intake_allows_patient_edits(intake_form.form_status):
        raise StateTransitionError(
            domain_message("other.domain.intake_signature_in_progress_only"),
            api_message_key="other.domain.intake_signature_in_progress_only",
        )

    # Strip data URL prefix if present
    data = signature_base64
    if "," in data:
        data = data.split(",", 1)[1]

    if len(data) > SIGNATURE_MAX_SIZE * 1.4:
        raise InvalidSignatureError(
            domain_message("other.domain.signature_payload_too_large_before_decode"),
            api_message_key="other.domain.signature_payload_too_large_before_decode",
        )

    try:
        raw = base64.b64decode(data, validate=True)
    except Exception:
        raise InvalidSignatureError(
            domain_message("other.domain.signature_invalid_base64"),
            api_message_key="other.domain.signature_invalid_base64",
        )
    if len(raw) == 0:
        raise InvalidSignatureError(
            domain_message("other.domain.signature_payload_empty"),
            api_message_key="other.domain.signature_payload_empty",
        )
    if len(raw) > SIGNATURE_MAX_SIZE:
        raise InvalidSignatureError(
            domain_message(
                "other.domain.signature_payload_too_large", max_bytes=SIGNATURE_MAX_SIZE
            ),
            api_message_key="other.domain.signature_payload_too_large",
            api_message_params={"max_bytes": SIGNATURE_MAX_SIZE},
        )

    # Dodana walidacja formatu za pomocą magic bytes
    is_png = raw.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = raw.startswith(b"\xff\xd8\xff")
    if not (is_png or is_jpeg):
        raise InvalidSignatureError(
            domain_message("other.domain.signature_image_format_invalid"),
            api_message_key="other.domain.signature_image_format_invalid",
        )

    sha256_hash = hashlib.sha256(raw).hexdigest()
    now = timezone.now()
    year_month = now.strftime("%Y/%m")
    rel_dir = (
        Path(getattr(settings, "SIGNATURES_RELATIVE_DIR", "signatures")) / year_month
    )
    dir_path = Path(settings.MEDIA_ROOT) / rel_dir
    dir_path.mkdir(parents=True, exist_ok=True)
    file_name = f"{intake_form_id}.png"
    file_path = dir_path / file_name
    file_path.write_bytes(raw)
    # Store path relative to MEDIA_ROOT for portability
    relative_path = str(rel_dir / file_name)

    intake_form.signature_file_path = relative_path
    intake_form.signature_sha256 = sha256_hash
    intake_form.save(
        update_fields=["signature_file_path", "signature_sha256", "updated_at"]
    )
    return intake_form


@transaction.atomic
def reopen_patient_intake_form(
    *,
    intake_form_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    reception_note: str = "",
    allowed_clinic_site_ids: Iterable[uuid.UUID] | None = None,
) -> PatientIntakeForm:
    """
    Move a submitted intake back to patient-editable state (REOPENED).

    Issues a fresh tablet session (latest-wins), wires it as the intake session,
    and records an optional reception note plus audit metadata.
    """
    intake_form = (
        PatientIntakeForm.objects.select_for_update()
        .select_related("session", "queue_entry", "queue_entry__daily_queue")
        .get(id=intake_form_id)
    )
    assert_intake_form_clinic_scope(
        intake_form=intake_form,
        allowed_clinic_site_ids=allowed_clinic_site_ids,
    )
    if intake_form.form_status == IntakeStatus.REOPENED:
        raise StateTransitionError(
            domain_message("other.domain.intake_reopen_already_open"),
            api_message_key="other.domain.intake_reopen_already_open",
        )
    if intake_form.form_status != IntakeStatus.SUBMITTED:
        raise StateTransitionError(
            domain_message("other.domain.intake_reopen_submitted_only"),
            api_message_key="other.domain.intake_reopen_submitted_only",
        )
    locale = (intake_form.session.form_locale or "de-DE")[:10]
    issue_tablet_session_latest_wins(
        queue_entry_id=intake_form.queue_entry_id,
        created_by_user_id=actor_user_id,
        form_locale=locale,
    )
    intake_form.refresh_from_db()
    now = timezone.now()
    note = (reception_note or "").strip()
    intake_form.form_status = IntakeStatus.REOPENED
    intake_form.reception_note = note
    intake_form.reception_note_updated_at = now
    intake_form.reception_note_updated_by_id = actor_user_id
    intake_form.save(
        update_fields=[
            "form_status",
            "reception_note",
            "reception_note_updated_at",
            "reception_note_updated_by_id",
            "updated_at",
        ]
    )
    queue_entry = intake_form.queue_entry
    create_audit_event(
        event_type="INTAKE_REOPENED",
        actor_user_id=actor_user_id,
        patient_id=queue_entry.patient_id,
        context_clinic_site_id=queue_entry.daily_queue.clinic_site_id,
        metadata={
            "intake_form_id": str(intake_form.id),
            "queue_entry_id": str(queue_entry.id),
            "session_id": str(intake_form.session_id),
            "reception_note": note,
        },
    )
    return intake_form


@transaction.atomic
def submit_patient_intake_form(
    *,
    intake_form_id: uuid.UUID,
    submitted_at: datetime | None = None,
    submitted_by_user_id: uuid.UUID | None = None,
    allowed_clinic_site_ids: Iterable[uuid.UUID] | None = None,
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
    intake_form = PatientIntakeForm.objects.select_related(
        "session",
        "queue_entry",
        "queue_entry__patient",
        "queue_entry__daily_queue",
    ).get(id=intake_form_id)
    assert_intake_form_clinic_scope(
        intake_form=intake_form,
        allowed_clinic_site_ids=allowed_clinic_site_ids,
    )
    session = intake_form.session
    queue_entry = QueueEntry.objects.select_for_update(of=("self",)).get(
        id=intake_form.queue_entry_id
    )
    now = submitted_at or timezone.now()

    if intake_form.form_status == IntakeStatus.SUBMITTED:
        return intake_form
    raise_if_queue_entry_cancelled(queue_entry)
    if not intake_allows_patient_edits(intake_form.form_status):
        raise StateTransitionError(
            domain_message("other.domain.intake_submit_in_progress_only"),
            api_message_key="other.domain.intake_submit_in_progress_only",
        )
    if not intake_form.signature_file_path:
        raise StateTransitionError(
            domain_message("other.domain.intake_submit_signature_required"),
            api_message_key="other.domain.intake_submit_signature_required",
        )

    if queue_entry.active_session_id != session.id:
        raise IntakeSessionValidationError(
            domain_message("other.domain.intake_session_not_active"),
            api_message_key="other.domain.intake_session_not_active",
        )
    if session.consumed_at is not None:
        raise IntakeSessionValidationError(
            domain_message("other.domain.intake_session_consumed"),
            api_message_key="other.domain.intake_session_consumed",
        )
    if session.expires_at <= now:
        raise IntakeSessionValidationError(
            domain_message("other.domain.intake_session_expired"),
            api_message_key="other.domain.intake_session_expired",
        )

    today = timezone.localdate(now)
    process_type = coerce_process_type(queue_entry.process_type)
    required_consent_ids = set(
        ConsentDefinition.objects.filter(
            _effective_consent_filter(today, process_type), is_required=True
        )
        .distinct()
        .values_list("id", flat=True)
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
        raise RequiredConsentMissingError(
            domain_message("other.domain.required_consents_not_accepted"),
            api_message_key="other.domain.required_consents_not_accepted",
        )

    if process_type == PROCESS_TYPE_TELEDERM:
        from apps.telederm.services import finalize_telederm_payload_on_submit

        finalized = finalize_telederm_payload_on_submit(
            intake_form,
            form_locale=(session.form_locale or "de-DE"),
            submitted_at=now,
        )
        intake_form.telederm_payload = finalized
        intake_form.telederm_schema_version = finalized.get("schema_version", 1)
        intake_form.save(
            update_fields=[
                "telederm_payload",
                "telederm_schema_version",
                "updated_at",
            ]
        )
    else:
        required_question_codes = set(
            AnamnesisQuestionDefinition.objects.filter(
                _effective_question_filter(today, process_type), is_required=True
            )
            .distinct()
            .values_list("code", flat=True)
        )
        answered_question_codes = _extract_answered_question_codes(
            intake_form.anamnesis_payload
        )
        missing_question_codes = required_question_codes - answered_question_codes
        if missing_question_codes:
            raise RequiredAnamnesisMissingError(
                domain_message("other.domain.required_anamnesis_not_answered"),
                api_message_key="other.domain.required_anamnesis_not_answered",
            )

    # Optimistic lock style transition: only one concurrent submit wins.
    updated_rows = PatientIntakeForm.objects.filter(
        id=intake_form.id,
        form_status__in=(
            IntakeStatus.IN_PROGRESS,
            IntakeStatus.REOPENED,
        ),
    ).update(
        form_status=IntakeStatus.SUBMITTED,
        submitted_at=now,
        updated_at=now,
    )
    if updated_rows == 0:
        refreshed = PatientIntakeForm.objects.get(id=intake_form.id)
        if refreshed.form_status == IntakeStatus.SUBMITTED:
            return refreshed
        raise StateTransitionError(
            domain_message("other.domain.intake_submit_in_progress_only"),
            api_message_key="other.domain.intake_submit_in_progress_only",
        )

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
    queue_entry.doctor_list_sort_at = now
    queue_entry.save(
        update_fields=["entry_status", "doctor_list_sort_at", "updated_at"]
    )

    # Lazy import: ``medical.services`` already imports this module at load time;
    # importing medical here at module level would risk a circular import.
    from apps.medical.services import (
        autorevoke_paper_intake_authorization_after_intake_submit,
    )

    autorevoke_paper_intake_authorization_after_intake_submit(
        queue_entry_id=queue_entry.id,
        intake_form_id=intake_form.id,
        actor_user_id=submitted_by_user_id,
    )

    create_audit_event(
        event_type="INTAKE_SUBMITTED",
        actor_user_id=submitted_by_user_id,
        patient_id=queue_entry.patient_id,
        context_clinic_site_id=queue_entry.daily_queue.clinic_site_id,
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
            "submitted_by_user_id": (
                str(submitted_by_user_id) if submitted_by_user_id else None
            ),
        },
    )

    return PatientIntakeForm.objects.get(id=intake_form.id)


@transaction.atomic
def save_intake_anamnesis_payload(
    *,
    intake_form_id: uuid.UUID,
    anamnesis_schema_version: int,
    answers_payload: list[dict],
    allowed_clinic_site_ids: Iterable[uuid.UUID] | None = None,
) -> PatientIntakeForm:
    """Persist validated anamnesis payload for in-progress intake form."""
    intake_form = (
        PatientIntakeForm.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=intake_form_id)
    )
    assert_intake_form_clinic_scope(
        intake_form=intake_form,
        allowed_clinic_site_ids=allowed_clinic_site_ids,
    )
    if not intake_allows_patient_edits(intake_form.form_status):
        raise StateTransitionError(
            domain_message("other.domain.intake_anamnesis_in_progress_only"),
            api_message_key="other.domain.intake_anamnesis_in_progress_only",
        )

    intake_form.anamnesis_schema_version = anamnesis_schema_version
    intake_form.anamnesis_payload = {
        "schema_version": anamnesis_schema_version,
        "answers": answers_payload,
    }
    intake_form.save(
        update_fields=["anamnesis_schema_version", "anamnesis_payload", "updated_at"]
    )
    return intake_form
