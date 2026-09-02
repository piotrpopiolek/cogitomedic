"""Extra branch coverage for telederm engine helpers."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.telederm.engine import (
    _evaluate_condition,
    active_path_code,
    answers_map,
    normalize_answer,
    triage_is_blocked,
    validate_required_answers,
    visible_questions,
)
from apps.telederm.engine import TeledermAnswerValue
from apps.telederm.services import load_catalog


class NormalizeAnswerTests(SimpleTestCase):
    def test_non_dict_returns_empty(self) -> None:
        self.assertEqual(normalize_answer("x").selected, ())

    def test_selected_as_string(self) -> None:
        self.assertEqual(normalize_answer({"selected": " YES "}).selected, ("YES",))
        self.assertEqual(normalize_answer({"selected": "  "}).selected, ())

    def test_selected_non_list_non_str(self) -> None:
        self.assertEqual(normalize_answer({"selected": 12}).selected, ())

    def test_free_text_stripped_to_none(self) -> None:
        self.assertIsNone(normalize_answer({"free_text": "  "}).free_text)
        self.assertEqual(normalize_answer({"free_text": " note "}).free_text, "note")

    def test_answers_map_rejects_non_dict(self) -> None:
        self.assertEqual(answers_map({"answers": ["nope"]}), {})


class EvaluateConditionTests(SimpleTestCase):
    def test_all_any_not_empty_and_unknown_op(self) -> None:
        answers = {
            "Q1": TeledermAnswerValue(selected=("YES",)),
            "Q2": TeledermAnswerValue(selected=(), free_text="hi"),
        }
        self.assertTrue(
            _evaluate_condition(
                {
                    "all": [
                        {"question_id": "Q1", "op": "eq", "value": "YES"},
                        {"question_id": "Q2", "op": "not_empty"},
                    ]
                },
                answers,
            )
        )
        self.assertTrue(
            _evaluate_condition(
                {
                    "any": [
                        {"question_id": "Q1", "op": "contains", "value": "yes"},
                        {"question_id": "missing", "op": "eq", "value": "NO"},
                    ]
                },
                answers,
            )
        )
        self.assertTrue(_evaluate_condition({}, answers))
        self.assertFalse(
            _evaluate_condition(
                {"question_id": "Q1", "op": "weird", "value": "YES"}, answers
            )
        )


class TeledermEngineBranchTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.catalog = load_catalog()

    def test_active_path_without_catalog_returns_option_code(self) -> None:
        payload = {"answers": {"CC001": {"selected": ["HAIR_LOSS"]}}}
        self.assertEqual(active_path_code(payload, None), "HAIR_LOSS")

    def test_triage_blocked_flag_short_circuits(self) -> None:
        self.assertTrue(triage_is_blocked({"triage_blocked": True}))

    def test_validate_when_triage_blocked_with_answer(self) -> None:
        payload = {"answers": {"T001": {"selected": ["SEVERE_PAIN"]}}}
        self.assertEqual(validate_required_answers(self.catalog, payload), [])

    def test_validate_when_triage_blocked_flag_without_t001(self) -> None:
        payload = {"triage_blocked": True, "answers": {}}
        self.assertEqual(validate_required_answers(self.catalog, payload), ["T001"])

    def test_inactive_question_not_visible(self) -> None:
        q = next(x for x in self.catalog if x.question_id == "Q001")
        q.is_active = False
        try:
            payload = {
                "answers": {
                    "T001": {"selected": ["NONE"]},
                    "CC001": {"selected": ["NEW_SKIN_LESION"]},
                }
            }
            visible_ids = [
                x.question_id for x in visible_questions(self.catalog, payload)
            ]
            self.assertNotIn("Q001", visible_ids)
        finally:
            q.is_active = True

    def test_show_if_other_reveals_follow_up(self) -> None:
        payload = {
            "answers": {
                "T001": {"selected": ["NONE"]},
                "CC001": {"selected": ["NEW_SKIN_LESION"]},
                "Q002": {"selected": ["OTHER"]},
            }
        }
        visible_ids = [q.question_id for q in visible_questions(self.catalog, payload)]
        self.assertIn("Q002a", visible_ids)

    def test_validate_required_free_text_follow_up(self) -> None:
        payload = {
            "answers": {
                "T001": {"selected": ["NONE"]},
                "CC001": {"selected": ["NEW_SKIN_LESION"]},
                "Q002": {"selected": ["OTHER"]},
            }
        }
        # Q002a is free text; if required would appear in missing — seed sets is_required default True on _q FREE_TEXT for Q002a
        missing = validate_required_answers(self.catalog, payload)
        self.assertIn("Q001", missing)
