"""Tests for telederm visibility engine and validation."""

from __future__ import annotations

from django.test import TestCase

from apps.telederm.engine import (
    active_path_code,
    triage_is_blocked,
    validate_required_answers,
    visible_questions,
)
from apps.telederm.services import load_catalog
from apps.telederm.tests.smoke_answers import SMOKE_TELEDERM_ANSWERS


class TeledermEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.catalog = load_catalog()

    def test_catalog_seed_contains_smoke_questions(self) -> None:
        question_ids = {q.question_id for q in self.catalog}
        self.assertIn("T001", question_ids)
        self.assertIn("CC001", question_ids)
        self.assertIn("Q001", question_ids)

    def test_triage_none_shows_chief_and_path(self) -> None:
        payload = {
            "answers": {
                "T001": {"selected": ["NONE"]},
                "CC001": {"selected": ["NEW_SKIN_LESION"]},
            }
        }
        self.assertFalse(triage_is_blocked(payload))
        visible_ids = [q.question_id for q in visible_questions(self.catalog, payload)]
        self.assertIn("T001", visible_ids)
        self.assertIn("CC001", visible_ids)
        self.assertIn("Q001", visible_ids)
        self.assertEqual(active_path_code(payload, self.catalog), "CCE-001")

    def test_triage_urgent_blocks_path(self) -> None:
        payload = {"answers": {"T001": {"selected": ["SEVERE_PAIN"]}}}
        self.assertTrue(triage_is_blocked(payload))
        visible_ids = [q.question_id for q in visible_questions(self.catalog, payload)]
        self.assertEqual(visible_ids, ["T001"])

    def test_validate_required_missing_chief(self) -> None:
        payload = {"answers": {"T001": {"selected": ["NONE"]}}}
        missing = validate_required_answers(self.catalog, payload)
        self.assertIn("CC001", missing)

    def test_validate_complete_smoke_path(self) -> None:
        payload = dict(SMOKE_TELEDERM_ANSWERS)
        self.assertEqual(validate_required_answers(self.catalog, payload), [])

    def test_stale_chief_complaint_path_does_not_override_cc001(self) -> None:
        payload = {
            "chief_complaint_path": "CCE-002",
            "answers": {
                "T001": {"selected": ["NONE"]},
                "CC001": {"selected": ["NEW_SKIN_LESION"]},
            },
        }
        visible_ids = [q.question_id for q in visible_questions(self.catalog, payload)]
        self.assertEqual(active_path_code(payload, self.catalog), "CCE-001")
        self.assertIn("Q001", visible_ids)
        self.assertNotIn("Q020", visible_ids)

    def test_hair_loss_cc001_ignores_mole_path_field(self) -> None:
        payload = {
            "chief_complaint_path": "CCE-002",
            "answers": {
                "T001": {"selected": ["NONE"]},
                "CC001": {"selected": ["HAIR_LOSS"]},
            },
        }
        visible_ids = [q.question_id for q in visible_questions(self.catalog, payload)]
        self.assertEqual(active_path_code(payload, self.catalog), "CCE-009")
        self.assertIn("Q160", visible_ids)
        self.assertNotIn("Q020", visible_ids)
