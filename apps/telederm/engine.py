"""Adaptive visibility and validation for telederm questionnaire."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from apps.telederm.models import TeledermQuestionDefinition, TeledermSection

TRIAGE_NONE_OPTION_CODE = "NONE"


@dataclass(frozen=True)
class TeledermAnswerValue:
    selected: tuple[str, ...]
    free_text: str | None = None


def normalize_answer(raw: Any) -> TeledermAnswerValue:
    if not isinstance(raw, dict):
        return TeledermAnswerValue(selected=())
    selected_raw = raw.get("selected") or raw.get("selected_option_codes") or []
    if isinstance(selected_raw, str):
        selected: tuple[str, ...] = (
            (selected_raw.strip(),) if selected_raw.strip() else ()
        )
    elif isinstance(selected_raw, list):
        selected = tuple(str(x).strip() for x in selected_raw if str(x).strip())
    else:
        selected = ()
    free_text = raw.get("free_text")
    if free_text is not None:
        free_text = str(free_text).strip() or None
    return TeledermAnswerValue(selected=selected, free_text=free_text)


def answers_map(payload: Mapping[str, Any]) -> dict[str, TeledermAnswerValue]:
    raw_answers = payload.get("answers") or {}
    if not isinstance(raw_answers, dict):
        return {}
    return {str(k): normalize_answer(v) for k, v in raw_answers.items()}


def active_path_code(
    payload: Mapping[str, Any],
    catalog: Sequence[TeledermQuestionDefinition] | None = None,
) -> str | None:
    """Path is derived only from CC001; inbound ``chief_complaint_path`` is ignored."""
    answers = answers_map(payload)
    cc = answers.get("CC001")
    if not cc or not cc.selected:
        return None
    selected_code = cc.selected[0]
    if catalog:
        cc_q = next((q for q in catalog if q.question_id == "CC001"), None)
        if cc_q is not None:
            for opt in cc_q.options.all():
                if opt.code == selected_code and opt.activates_path_code:
                    return opt.activates_path_code
    return str(selected_code)


def triage_is_blocked(payload: Mapping[str, Any]) -> bool:
    if payload.get("triage_blocked") is True:
        return True
    answers = answers_map(payload)
    triage = answers.get("T001")
    if not triage or not triage.selected:
        return False
    if TRIAGE_NONE_OPTION_CODE in triage.selected and len(triage.selected) == 1:
        return False
    return any(code != TRIAGE_NONE_OPTION_CODE for code in triage.selected)


def _evaluate_condition(
    condition: Mapping[str, Any], answers: Mapping[str, TeledermAnswerValue]
) -> bool:
    if "all" in condition:
        parts = condition["all"]
        return all(
            _evaluate_condition(part, answers)
            for part in parts
            if isinstance(part, dict)
        )
    if "any" in condition:
        parts = condition["any"]
        return any(
            _evaluate_condition(part, answers)
            for part in parts
            if isinstance(part, dict)
        )
    question_id = condition.get("question_id")
    if not question_id:
        return True
    answer = answers.get(str(question_id))
    if answer is None:
        return False
    op = str(condition.get("op", "eq"))
    value = str(condition.get("value", "")).strip().lower()
    selected_lower = {s.lower() for s in answer.selected}
    if op == "eq":
        return value in selected_lower
    if op == "contains":
        return value in selected_lower
    if op == "not_empty":
        return bool(answer.selected or answer.free_text)
    return False


def question_is_visible(
    question: TeledermQuestionDefinition,
    *,
    answers: Mapping[str, TeledermAnswerValue],
    path_code: str | None,
) -> bool:
    if not question.is_active:
        return False
    if question.section == TeledermSection.TRIAGE:
        return True
    if question.section == TeledermSection.CHIEF_COMPLAINT:
        triage = answers.get("T001")
        if triage and triage.selected:
            if triage_is_blocked(
                {
                    "answers": {
                        "T001": {
                            "selected": list(triage.selected),
                            "free_text": triage.free_text,
                        }
                    }
                }
            ):
                return False
        return True
    if question.path_code in {"TRIAGE", "CHIEF"}:
        return question.section in {
            TeledermSection.TRIAGE,
            TeledermSection.CHIEF_COMPLAINT,
        }
    if path_code is None:
        return False
    if question.path_code == "GLOBAL":
        if path_code in {"TRIAGE", "CHIEF"}:
            return False
    elif question.path_code != path_code:
        return False
    show_if = question.show_if or {}
    if not show_if:
        return True
    return _evaluate_condition(show_if, answers)


def visible_questions(
    catalog: Sequence[TeledermQuestionDefinition],
    payload: Mapping[str, Any],
) -> list[TeledermQuestionDefinition]:
    answers = answers_map(payload)
    path = active_path_code(payload, catalog)
    if triage_is_blocked(payload):
        return [
            q for q in catalog if q.section == TeledermSection.TRIAGE and q.is_active
        ]
    out: list[TeledermQuestionDefinition] = []
    for question in catalog:
        if question_is_visible(question, answers=answers, path_code=path):
            out.append(question)
    return out


def validate_required_answers(
    catalog: Sequence[TeledermQuestionDefinition],
    payload: Mapping[str, Any],
) -> list[str]:
    """Return missing required question_ids."""
    if triage_is_blocked(payload):
        triage = answers_map(payload).get("T001")
        if triage and triage.selected:
            return []
        return ["T001"]
    answers = answers_map(payload)
    missing: list[str] = []
    for question in visible_questions(catalog, payload):
        if not question.is_required:
            continue
        answer = answers.get(question.question_id)
        if question.answer_type == "FREE_TEXT":
            if not answer or not answer.free_text:
                missing.append(question.question_id)
            continue
        if not answer or not answer.selected:
            missing.append(question.question_id)
    return missing
