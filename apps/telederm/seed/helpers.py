"""Shared helpers and reusable option sets for telederm catalog seeds."""

from __future__ import annotations

from typing import Any

from apps.telederm.models import TeledermAnswerType, TeledermSection


def _choice_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    return value.value


def _opt(
    code: str,
    *,
    label_de: str,
    label_en: str,
    label_pl: str,
    is_urgent: bool = False,
    activates_path_code: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "code": code,
        "label_de": label_de,
        "label_en": label_en,
        "label_pl": label_pl,
        "is_urgent": is_urgent,
    }
    if activates_path_code:
        row["activates_path_code"] = activates_path_code
    return row


def _q(
    question_id: str,
    *,
    path_code: str,
    section: Any = TeledermSection.QUESTIONNAIRE,
    answer_type: Any,
    text_de: str,
    text_en: str,
    text_pl: str,
    show_if: dict[str, Any] | None = None,
    include_in_summary: bool = True,
    is_required: bool = True,
    display_order: int,
    options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "path_code": path_code,
        "section": _choice_str(section),
        "answer_type": _choice_str(answer_type),
        "question_text_de": text_de,
        "question_text_en": text_en,
        "question_text_pl": text_pl,
        "show_if": show_if or {},
        "include_in_summary": include_in_summary,
        "is_required": is_required,
        "display_order": display_order,
        "options": options or [],
    }


def _ft(
    question_id: str,
    *,
    path_code: str,
    text_de: str,
    text_en: str,
    text_pl: str,
    display_order: int,
    show_if: dict[str, Any] | None = None,
    is_required: bool = False,
) -> dict[str, Any]:
    return _q(
        question_id,
        path_code=path_code,
        answer_type=TeledermAnswerType.FREE_TEXT,
        text_de=text_de,
        text_en=text_en,
        text_pl=text_pl,
        display_order=display_order,
        show_if=show_if,
        is_required=is_required,
    )


# --- Reusable answer sets ---------------------------------------------------

YES = _opt("YES", label_de="Ja", label_en="Yes", label_pl="Tak")
NO = _opt("NO", label_de="Nein", label_en="No", label_pl="Nie")
UNKNOWN = _opt(
    "UNKNOWN", label_de="Weiß nicht", label_en="Don't know", label_pl="Nie wiem"
)
NONE = _opt("NONE", label_de="Keine", label_en="None", label_pl="Brak")
OTHER = _opt("OTHER", label_de="Sonstiges", label_en="Other", label_pl="Inne")
NOT_APPLICABLE = _opt(
    "NOT_APPLICABLE",
    label_de="Nicht zutreffend",
    label_en="Not applicable",
    label_pl="Nie dotyczy",
)

YES_NO = [YES, NO]
YES_NO_UNKNOWN = [YES, NO, UNKNOWN]
YES_NO_NOT_APPLICABLE = [YES, NO, NOT_APPLICABLE]

DURATION_ONSET = [
    _opt("TODAY", label_de="Heute", label_en="Today", label_pl="Dzisiaj"),
    _opt(
        "TWO_TO_SEVEN_DAYS",
        label_de="2–7 Tage",
        label_en="2–7 days",
        label_pl="2–7 dni",
    ),
    _opt(
        "ONE_TO_FOUR_WEEKS",
        label_de="1–4 Wochen",
        label_en="1–4 weeks",
        label_pl="1–4 tygodnie",
    ),
    _opt(
        "ONE_TO_SIX_MONTHS",
        label_de="1–6 Monate",
        label_en="1–6 months",
        label_pl="1–6 miesięcy",
    ),
    _opt(
        "OVER_SIX_MONTHS",
        label_de="Länger als 6 Monate",
        label_en="More than 6 months",
        label_pl="Ponad 6 miesięcy",
    ),
    UNKNOWN,
]

DURATION_UNDER_SEVEN = [
    _opt(
        "UNDER_SEVEN_DAYS",
        label_de="Weniger als 7 Tage",
        label_en="Less than 7 days",
        label_pl="Mniej niż 7 dni",
    ),
    _opt(
        "ONE_TO_FOUR_WEEKS",
        label_de="1–4 Wochen",
        label_en="1–4 weeks",
        label_pl="1–4 tygodnie",
    ),
    _opt(
        "ONE_TO_SIX_MONTHS",
        label_de="1–6 Monate",
        label_en="1–6 months",
        label_pl="1–6 miesięcy",
    ),
    _opt(
        "OVER_SIX_MONTHS",
        label_de="Länger als 6 Monate",
        label_en="More than 6 months",
        label_pl="Ponad 6 miesięcy",
    ),
    UNKNOWN,
]

PREGNANCY = [
    YES,
    NO,
    NOT_APPLICABLE,
]

CONSULTATION_EXPECTATIONS = [
    _opt(
        "LESION_ASSESSMENT",
        label_de="Beurteilung der Veränderung",
        label_en="Assessment of the lesion",
        label_pl="Ocena zmiany",
    ),
    _opt(
        "TREATMENT",
        label_de="Behandlung",
        label_en="Treatment",
        label_pl="Leczenie",
    ),
    _opt(
        "PRESCRIPTION_IF_INDICATED",
        label_de="Rezept, falls angezeigt",
        label_en="Prescription if indicated",
        label_pl="Recepta, jeśli wskazana",
    ),
    _opt(
        "SECOND_OPINION",
        label_de="Zweite Meinung",
        label_en="Second opinion",
        label_pl="Druga opinia",
    ),
    _opt(
        "FURTHER_RECOMMENDATIONS",
        label_de="Weitere Empfehlungen",
        label_en="Further recommendations",
        label_pl="Dalsze zalecenia",
    ),
]

ADDITIONAL_INFO = _ft(
    "Q_ADDITIONAL",
    path_code="PLACEHOLDER",
    text_de="Zusätzliche Information für den Arzt.",
    text_en="Additional information for the doctor.",
    text_pl="Dodatkowa informacja dla lekarza.",
    display_order=9990,
    is_required=False,
)
