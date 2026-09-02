"""Coverage for clinical summary locale and triage branches."""

from __future__ import annotations

from django.test import TestCase

from apps.telederm.clinical_summary import build_clinical_summary
from apps.telederm.engine import TeledermAnswerValue
from apps.telederm.clinical_summary import (
    _format_answer,
    _label_for_option,
    _question_text,
)
from apps.telederm.services import load_catalog
from apps.telederm.tests.smoke_answers import SMOKE_TELEDERM_ANSWERS


class ClinicalSummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.catalog = load_catalog()
        cls.cc = next(q for q in cls.catalog if q.question_id == "CC001")
        cls.q_ft = next(
            (q for q in cls.catalog if q.answer_type == "FREE_TEXT"),
            None,
        )

    def test_triage_blocked_summary(self) -> None:
        summary = build_clinical_summary(
            catalog=self.catalog,
            payload={"answers": {"T001": {"selected": ["SEVERE_PAIN"]}}},
            locale="de-DE",
        )
        self.assertTrue(summary["triage_blocked"])
        self.assertEqual(summary["lines"], [])

    def test_locale_pl_and_en_labels(self) -> None:
        opt = self.cc.options.first()
        assert opt is not None
        self.assertEqual(
            _label_for_option(self.cc, opt.code, "pl-PL"),
            opt.label_pl or opt.label_de,
        )
        self.assertEqual(
            _label_for_option(self.cc, opt.code, "en-US"),
            opt.label_en or opt.label_de,
        )
        self.assertEqual(_label_for_option(self.cc, "NO_SUCH", "de-DE"), "NO_SUCH")
        self.assertTrue(_question_text(self.cc, "pl-PL"))
        self.assertTrue(_question_text(self.cc, "en-US"))

    def test_format_answer_branches(self) -> None:
        self.assertEqual(_format_answer(self.cc, None, "de-DE"), "—")
        self.assertEqual(
            _format_answer(self.cc, TeledermAnswerValue(selected=()), "de-DE"),
            "—",
        )
        if self.q_ft is not None:
            self.assertEqual(
                _format_answer(
                    self.q_ft, TeledermAnswerValue(selected=(), free_text=None), "de-DE"
                ),
                "—",
            )
            self.assertEqual(
                _format_answer(
                    self.q_ft,
                    TeledermAnswerValue(selected=(), free_text="note"),
                    "de-DE",
                ),
                "note",
            )
        labeled = _format_answer(
            self.cc,
            TeledermAnswerValue(selected=("NEW_SKIN_LESION",), free_text="x"),
            "de-DE",
        )
        self.assertIn("—", labeled)

    def test_smoke_summary_has_problem_label(self) -> None:
        summary = build_clinical_summary(
            catalog=self.catalog,
            payload=SMOKE_TELEDERM_ANSWERS,
            locale="de-DE",
        )
        self.assertFalse(summary["triage_blocked"])
        self.assertEqual(summary["path_code"], "CCE-001")
        self.assertTrue(summary["problem_label"])
