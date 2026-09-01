"""Build structured Clinical Summary for doctor panel."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from apps.telederm.engine import (
    TeledermAnswerValue,
    active_path_code,
    answers_map,
    triage_is_blocked,
)
from apps.telederm.models import TeledermQuestionDefinition, TeledermSection


def _label_for_option(question: TeledermQuestionDefinition, code: str, locale: str) -> str:
    for opt in question.options.all():
        if opt.code == code:
            if locale.startswith("pl") and opt.label_pl.strip():
                return opt.label_pl
            if locale.startswith("en") and opt.label_en.strip():
                return opt.label_en
            return opt.label_de
    return code


def _question_text(question: TeledermQuestionDefinition, locale: str) -> str:
    if locale.startswith("pl") and question.question_text_pl.strip():
        return question.question_text_pl
    if locale.startswith("en") and question.question_text_en.strip():
        return question.question_text_en
    return question.question_text_de


def _format_answer(
    question: TeledermQuestionDefinition,
    answer: TeledermAnswerValue | None,
    locale: str,
) -> str:
    if answer is None:
        return "—"
    if question.answer_type == "FREE_TEXT":
        return answer.free_text or "—"
    if not answer.selected:
        return "—"
    labels = [_label_for_option(question, code, locale) for code in answer.selected]
    text = ", ".join(labels)
    if answer.free_text:
        text = f"{text} — {answer.free_text}" if text else answer.free_text
    return text or "—"


def build_clinical_summary(
    *,
    catalog: Sequence[TeledermQuestionDefinition],
    payload: Mapping[str, Any],
    locale: str = "de-DE",
) -> dict[str, Any]:
    """Structured summary for doctor read-only panel."""
    answers = answers_map(payload)
    path = active_path_code(payload, catalog)
    if triage_is_blocked(payload):
        return {
            "schema_version": 1,
            "triage_blocked": True,
            "path_code": None,
            "problem_label": "",
            "lines": [],
            "message_key": "waiting_room.form.telederm_triage_blocked",
        }

    lines: list[dict[str, str]] = []
    problem_label = ""
    for question in catalog:
        if not question.include_in_summary:
            continue
        if question.section == TeledermSection.CHIEF_COMPLAINT:
            answer = answers.get(question.question_id)
            if answer and answer.selected:
                problem_label = _format_answer(question, answer, locale)
            continue
        if question.path_code != path:
            continue
        answer = answers.get(question.question_id)
        if answer is None and question.answer_type != "FREE_TEXT":
            continue
        lines.append(
            {
                "question_id": question.question_id,
                "label": _question_text(question, locale),
                "value": _format_answer(question, answer, locale),
            }
        )

    return {
        "schema_version": 1,
        "triage_blocked": False,
        "path_code": path,
        "problem_label": problem_label,
        "lines": lines,
    }
