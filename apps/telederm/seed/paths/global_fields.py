"""Global questionnaire fields (G001–G005) shared across telederm paths."""

from __future__ import annotations

from typing import Any

from apps.telederm.models import TeledermAnswerType, TeledermSection
from apps.telederm.seed.helpers import NO, NOT_APPLICABLE, OTHER, YES, YES_NO, _ft, _opt, _q

PATH_CODE = "GLOBAL"
BASE_ORDER = 16000

GLOBAL_FIELDS_CATALOG: list[dict[str, Any]] = [
    _q(
        "G001",
        path_code=PATH_CODE,
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=BASE_ORDER,
        text_de="Nehmen Sie derzeit Medikamente ein?",
        text_en="Are you currently taking any medications?",
        text_pl="Czy przyjmuje Pan/Pani aktualnie leki?",
        options=YES_NO,
    ),
    _ft(
        "G001a",
        path_code=PATH_CODE,
        display_order=BASE_ORDER + 5,
        text_de="Welche Medikamente?",
        text_en="Which medications?",
        text_pl="Jakie leki?",
        show_if={"question_id": "G001", "op": "eq", "value": "YES"},
    ),
    _q(
        "G002",
        path_code=PATH_CODE,
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=BASE_ORDER + 10,
        text_de="Sind Ihnen Allergien bekannt?",
        text_en="Do you have any known allergies?",
        text_pl="Czy ma Pan/Pani znane alergie?",
        options=YES_NO,
    ),
    _ft(
        "G002a",
        path_code=PATH_CODE,
        display_order=BASE_ORDER + 15,
        text_de="Welche Allergien?",
        text_en="Which allergies?",
        text_pl="Jakie alergie?",
        show_if={"question_id": "G002", "op": "eq", "value": "YES"},
    ),
    _q(
        "G003",
        path_code=PATH_CODE,
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=BASE_ORDER + 20,
        text_de="Sind Sie schwanger oder stillen Sie?",
        text_en="Are you pregnant or breastfeeding?",
        text_pl="Czy jest Pani w ciąży lub karmi piersią?",
        options=[
            NO,
            _opt(
                "PREGNANCY",
                label_de="Schwangerschaft",
                label_en="Pregnancy",
                label_pl="Ciąża",
            ),
            _opt(
                "BREASTFEEDING",
                label_de="Stillen",
                label_en="Breastfeeding",
                label_pl="Karmienie",
            ),
            NOT_APPLICABLE,
        ],
    ),
    _q(
        "G004",
        path_code=PATH_CODE,
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.MULTIPLE,
        display_order=BASE_ORDER + 30,
        text_de="Besteht eine Immunsuppression?",
        text_en="Do you have immunosuppression?",
        text_pl="Czy występuje immunosupresja?",
        options=[
            _opt("NONE", label_de="Nein", label_en="No", label_pl="Nie"),
            _opt(
                "MEDICATIONS",
                label_de="Medikamente",
                label_en="Medications",
                label_pl="Leki",
            ),
            _opt(
                "TRANSPLANT",
                label_de="Transplantation",
                label_en="Transplant",
                label_pl="Przeszczep",
            ),
            _opt(
                "ONCOLOGY",
                label_de="Onkologie",
                label_en="Oncology",
                label_pl="Onkologia",
            ),
            _opt("HIV", label_de="HIV", label_en="HIV", label_pl="HIV"),
            OTHER,
        ],
    ),
    _ft(
        "G005",
        path_code=PATH_CODE,
        display_order=BASE_ORDER + 40,
        text_de="Zusätzliche Informationen für den Arzt.",
        text_en="Additional information for the doctor.",
        text_pl="Dodatkowe informacje dla lekarza.",
        is_required=False,
    ),
]
