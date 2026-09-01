"""Seed questions for telederm path CCE-009 (hair loss)."""

from __future__ import annotations

from typing import Any

from apps.telederm.models import TeledermAnswerType, TeledermSection
from apps.telederm.seed.helpers import (
    NO,
    NONE,
    UNKNOWN,
    YES_NO,
    YES_NO_UNKNOWN,
    _ft,
    _opt,
    _q,
)

CCE009_QUESTIONS: list[dict[str, Any]] = [
    _q(
        "Q160",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=9000,
        text_de="Was ist das Hauptproblem?",
        text_en="What is the main problem?",
        text_pl="Jaki jest główny problem?",
        options=[
            _opt(
                "UNIFORM_HAIR_LOSS",
                label_de="Gleichmäßiger Haarausfall",
                label_en="Even hair loss",
                label_pl="Włosy wypadają równomiernie",
            ),
            _opt(
                "BALD_PATCHES",
                label_de="Kahle Stellen",
                label_en="Bald patches",
                label_pl="Powstały łyse placki",
            ),
            _opt(
                "THINNING_HAIRLINE",
                label_de="Ausdünnung am Haaransatz",
                label_en="Thinning hairline",
                label_pl="Przerzedza się linia włosów",
            ),
            _opt(
                "THINNING_CROWN",
                label_de="Ausdünnung am Scheitel",
                label_en="Thinning at the crown",
                label_pl="Przerzedza się czubek głowy",
            ),
            _opt(
                "HAIR_BREAKAGE",
                label_de="Haare brechen ab",
                label_en="Hair breakage",
                label_pl="Łamią się włosy",
            ),
            UNKNOWN,
        ],
    ),
    _q(
        "Q161",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=9010,
        text_de="Seit wann?",
        text_en="Since when?",
        text_pl="Od kiedy?",
        options=[
            _opt(
                "UNDER_ONE_MONTH",
                label_de="Weniger als 1 Monat",
                label_en="Less than 1 month",
                label_pl="<1 mies.",
            ),
            _opt(
                "ONE_TO_THREE_MONTHS",
                label_de="1–3 Monate",
                label_en="1–3 months",
                label_pl="1–3 mies.",
            ),
            _opt(
                "THREE_TO_SIX_MONTHS",
                label_de="3–6 Monate",
                label_en="3–6 months",
                label_pl="3–6 mies.",
            ),
            _opt(
                "OVER_SIX_MONTHS",
                label_de="Länger als 6 Monate",
                label_en="More than 6 months",
                label_pl=">6 mies.",
            ),
        ],
    ),
    _q(
        "Q162",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=9020,
        text_de="Ist das Problem plötzlich aufgetreten?",
        text_en="Did the problem start suddenly?",
        text_pl="Czy problem pojawił się nagle?",
        options=YES_NO,
    ),
    _q(
        "Q163",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.MULTIPLE,
        display_order=9030,
        text_de="Juckt, schmerzt oder schuppt sich die Kopfhaut?",
        text_en="Does the scalp itch, hurt, or flake?",
        text_pl="Czy skóra głowy swędzi, boli lub łuszczy się?",
        options=[
            _opt("ITCHING", label_de="Jucken", label_en="Itching", label_pl="Świąd"),
            _opt("PAIN", label_de="Schmerz", label_en="Pain", label_pl="Ból"),
            _opt(
                "FLAKING",
                label_de="Schuppung",
                label_en="Flaking",
                label_pl="Łuszczenie",
            ),
            _opt(
                "REDNESS",
                label_de="Rötung",
                label_en="Redness",
                label_pl="Zaczerwienienie",
            ),
            NONE,
        ],
    ),
    _q(
        "Q164",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.MULTIPLE,
        display_order=9040,
        text_de=(
            "Traten in den letzten 6 Monaten folgende Ereignisse auf: "
            "Schwangerschaft/Geburt, schwere Erkrankung, Operation, "
            "großer Stress oder deutlicher Gewichtsverlust?"
        ),
        text_en=(
            "In the last 6 months, did any of the following occur: "
            "pregnancy/childbirth, serious illness, surgery, major stress, "
            "or significant weight loss?"
        ),
        text_pl=(
            "Czy w ostatnich 6 miesiącach wystąpiły: ciąża/poród, ciężka choroba, "
            "operacja, duży stres lub znaczna utrata masy ciała?"
        ),
        options=[
            _opt(
                "PREGNANCY_CHILDBIRTH",
                label_de="Schwangerschaft/Geburt",
                label_en="Pregnancy/childbirth",
                label_pl="Ciąża/poród",
            ),
            _opt(
                "ILLNESS",
                label_de="Schwere Erkrankung",
                label_en="Serious illness",
                label_pl="Choroba",
            ),
            _opt(
                "SURGERY",
                label_de="Operation",
                label_en="Surgery",
                label_pl="Operacja",
            ),
            _opt("STRESS", label_de="Stress", label_en="Stress", label_pl="Stres"),
            _opt(
                "WEIGHT_LOSS",
                label_de="Gewichtsverlust",
                label_en="Weight loss",
                label_pl="Utrata masy",
            ),
            _opt(
                "NOTHING",
                label_de="Nichts",
                label_en="Nothing",
                label_pl="Nic",
            ),
        ],
    ),
    _q(
        "Q165",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=9050,
        text_de="Wurden neue Medikamente eingeführt?",
        text_en="Have new medications been started?",
        text_pl="Czy wprowadzono nowe leki?",
        options=YES_NO,
    ),
    _ft(
        "Q165a",
        path_code="CCE-009",
        display_order=9055,
        text_de="Welche?",
        text_en="Which ones?",
        text_pl="Jakie?",
        show_if={"question_id": "Q165", "op": "eq", "value": "YES"},
    ),
    _q(
        "Q166",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.MULTIPLE,
        display_order=9060,
        text_de="Liegen Schilddrüsenerkrankungen, Anämie oder Mangelzustände vor?",
        text_en="Do you have thyroid disease, anemia, or deficiencies?",
        text_pl="Czy występują choroby tarczycy, anemia lub niedobory?",
        options=[
            _opt(
                "THYROID",
                label_de="Schilddrüse",
                label_en="Thyroid disease",
                label_pl="Tarczyca",
            ),
            _opt(
                "ANEMIA",
                label_de="Anämie",
                label_en="Anemia",
                label_pl="Anemia",
            ),
            _opt(
                "DEFICIENCIES",
                label_de="Mangelzustände",
                label_en="Deficiencies",
                label_pl="Niedobory",
            ),
            NO,
            UNKNOWN,
        ],
    ),
    _q(
        "Q167",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=9070,
        text_de="Tritt ein ähnliches Problem in der Familie auf?",
        text_en="Has a similar problem occurred in your family?",
        text_pl="Czy podobny problem występował w rodzinie?",
        options=YES_NO_UNKNOWN,
    ),
    _q(
        "Q168",
        path_code="CCE-009",
        section=TeledermSection.QUESTIONNAIRE,
        answer_type=TeledermAnswerType.SINGLE,
        display_order=9080,
        text_de="Wurde bereits eine Behandlung angewendet?",
        text_en="Has treatment already been tried?",
        text_pl="Czy stosowano już leczenie?",
        options=YES_NO,
    ),
    _ft(
        "Q168a",
        path_code="CCE-009",
        display_order=9085,
        text_de="Welche?",
        text_en="Which treatment?",
        text_pl="Jakie?",
        show_if={"question_id": "Q168", "op": "eq", "value": "YES"},
    ),
]
