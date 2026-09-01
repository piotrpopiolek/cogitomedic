"""Telederm catalog and payload services."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Iterable, Mapping

from django.db.models import Prefetch
from django.utils import timezone

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.intake.models import PatientIntakeForm
from apps.reception.process_types import PROCESS_TYPE_TELEDERM, coerce_process_type
from apps.telederm.clinical_summary import build_clinical_summary
from apps.telederm.engine import (
    active_path_code,
    triage_is_blocked,
    validate_required_answers,
    visible_questions,
)
from apps.telederm.models import (
    TeledermQuestionDefinition,
    TeledermQuestionOption,
    TeledermSection,
)

TELEDERM_PAYLOAD_SCHEMA_VERSION = 1


class RequiredTeledermMissingError(DomainError):
    """Raised when required telederm answers are missing on submit."""


def load_catalog() -> list[TeledermQuestionDefinition]:
    return list(
        TeledermQuestionDefinition.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch(
                "options",
                queryset=TeledermQuestionOption.objects.order_by(
                    "display_order", "code"
                ),
            )
        )
        .order_by("display_order", "question_id")
    )


def _option_label(opt: TeledermQuestionOption, locale: str) -> str:
    if locale.startswith("pl") and opt.label_pl.strip():
        return opt.label_pl
    if locale.startswith("en") and opt.label_en.strip():
        return opt.label_en
    return opt.label_de


def _question_label(q: TeledermQuestionDefinition, locale: str) -> str:
    if locale.startswith("pl") and q.question_text_pl.strip():
        return q.question_text_pl
    if locale.startswith("en") and q.question_text_en.strip():
        return q.question_text_en
    return q.question_text_de


def serialize_catalog_for_tablet(
    *,
    catalog: Iterable[TeledermQuestionDefinition],
    payload: Mapping[str, Any],
    locale: str,
) -> dict[str, Any]:
    visible = visible_questions(list(catalog), payload)
    questions_payload: list[dict[str, Any]] = []
    for q in visible:
        options = [
            {
                "code": o.code,
                "label": _option_label(o, locale),
                "is_urgent": o.is_urgent,
                "activates_path_code": o.activates_path_code or None,
            }
            for o in q.options.all()
        ]
        raw_answer = (payload.get("answers") or {}).get(q.question_id) or {}
        questions_payload.append(
            {
                "question_id": q.question_id,
                "path_code": q.path_code,
                "section": q.section,
                "answer_type": q.answer_type,
                "question_text": _question_label(q, locale),
                "is_required": q.is_required,
                "show_if": q.show_if or {},
                "options": options,
                "answer": {
                    "selected": raw_answer.get("selected")
                    or raw_answer.get("selected_option_codes")
                    or [],
                    "free_text": raw_answer.get("free_text"),
                },
            }
        )
    path = active_path_code(payload, catalog)
    return {
        "schema_version": TELEDERM_PAYLOAD_SCHEMA_VERSION,
        "chief_complaint_path": path,
        "triage_blocked": triage_is_blocked(payload),
        "questions": questions_payload,
        "clinical_summary_preview": build_clinical_summary(
            catalog=list(catalog), payload=payload, locale=locale
        ),
    }


def normalize_telederm_payload(
    *,
    payload: Mapping[str, Any],
    catalog: list[TeledermQuestionDefinition],
    locale: str,
) -> dict[str, Any]:
    answers_in = payload.get("answers") or {}
    if not isinstance(answers_in, dict):
        answers_in = {}
    normalized_answers: dict[str, Any] = {}
    cc_path: str | None = payload.get("chief_complaint_path")
    if cc_path is not None:
        cc_path = str(cc_path) or None
    for qid, raw in answers_in.items():
        if not isinstance(raw, dict):
            continue
        selected = raw.get("selected") or raw.get("selected_option_codes") or []
        if isinstance(selected, str):
            selected = [selected] if selected.strip() else []
        normalized_answers[str(qid)] = {
            "selected": [str(x).strip() for x in selected if str(x).strip()],
            "free_text": (str(raw.get("free_text")).strip() if raw.get("free_text") else None),
        }
    cc_answer = normalized_answers.get("CC001")
    if cc_path is None and cc_answer and cc_answer["selected"]:
        selected_code = cc_answer["selected"][0]
        cc_q = next((q for q in catalog if q.question_id == "CC001"), None)
        if cc_q:
            for opt in cc_q.options.all():
                if opt.code == selected_code and opt.activates_path_code:
                    cc_path = opt.activates_path_code
                    break
        if cc_path is None:
            cc_path = selected_code

    draft = {
        "schema_version": TELEDERM_PAYLOAD_SCHEMA_VERSION,
        "engine": "telederm",
        "answers": normalized_answers,
        "chief_complaint_path": cc_path,
        "triage_blocked": False,
    }
    draft["triage_blocked"] = triage_is_blocked(draft)
    if not draft["triage_blocked"]:
        draft["clinical_summary"] = build_clinical_summary(
            catalog=catalog, payload=draft, locale=locale
        )
    return draft


def validate_telederm_for_submit(
    *,
    catalog: list[TeledermQuestionDefinition],
    payload: Mapping[str, Any],
) -> None:
    missing = validate_required_answers(catalog, payload)
    if missing:
        raise RequiredTeledermMissingError(
            domain_message(
                "other.domain.required_telederm_not_answered",
                questions=",".join(missing),
            ),
            api_message_key="other.domain.required_telederm_not_answered",
            api_message_params={"questions": ",".join(missing)},
        )
    if triage_is_blocked(payload):
        raise RequiredTeledermMissingError(
            domain_message("other.domain.telederm_triage_blocked"),
            api_message_key="other.domain.telederm_triage_blocked",
        )


def assert_telederm_intake_form(intake_form: PatientIntakeForm) -> str:
    process_type = coerce_process_type(intake_form.queue_entry.process_type)
    if process_type != PROCESS_TYPE_TELEDERM:
        raise DomainError(
            domain_message("other.domain.not_telederm_intake"),
            api_message_key="other.domain.not_telederm_intake",
        )
    return process_type


def save_telederm_payload(
    *,
    intake_form_id: uuid.UUID,
    payload: Mapping[str, Any],
    form_locale: str = "de-DE",
    allowed_clinic_site_ids: Iterable[uuid.UUID] | None = None,
) -> PatientIntakeForm:
    from apps.intake.services import (
        StateTransitionError,
        _assert_intake_form_clinic_scope,
        _intake_allows_patient_edits,
    )

    intake_form = (
        PatientIntakeForm.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=intake_form_id)
    )
    _assert_intake_form_clinic_scope(
        intake_form=intake_form,
        allowed_clinic_site_ids=allowed_clinic_site_ids,
    )
    assert_telederm_intake_form(intake_form)
    if not _intake_allows_patient_edits(intake_form.form_status):
        raise StateTransitionError(
            domain_message("other.domain.intake_telederm_in_progress_only"),
            api_message_key="other.domain.intake_telederm_in_progress_only",
        )
    catalog = load_catalog()
    normalized = normalize_telederm_payload(
        payload=payload, catalog=catalog, locale=form_locale
    )
    intake_form.telederm_schema_version = TELEDERM_PAYLOAD_SCHEMA_VERSION
    intake_form.telederm_payload = normalized
    intake_form.save(
        update_fields=["telederm_schema_version", "telederm_payload", "updated_at"]
    )
    return intake_form


def finalize_telederm_payload_on_submit(
    intake_form: PatientIntakeForm,
    *,
    form_locale: str,
    submitted_at: datetime | None = None,
) -> dict[str, Any]:
    catalog = load_catalog()
    payload = intake_form.telederm_payload or {}
    normalized = normalize_telederm_payload(
        payload=payload, catalog=catalog, locale=form_locale
    )
    normalized["submitted_at"] = (submitted_at or timezone.now()).isoformat()
    validate_telederm_for_submit(catalog=catalog, payload=normalized)
    return normalized
