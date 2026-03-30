"""Unit tests for apps/medical/befund_text.py — pure Python, no DB needed."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.medical.befund_text import (
    _format_lesion_numbers,
    _join_features,
    _locale_is_de,
    generate_befund_text,
)


class LocaleHelperTests(SimpleTestCase):
    def test_de_DE_is_german(self) -> None:
        self.assertTrue(_locale_is_de("de-DE"))

    def test_de_lowercase_is_german(self) -> None:
        self.assertTrue(_locale_is_de("de"))

    def test_empty_string_defaults_to_german(self) -> None:
        self.assertTrue(_locale_is_de(""))

    def test_en_US_is_not_german(self) -> None:
        self.assertFalse(_locale_is_de("en-US"))

    def test_pl_PL_is_not_german(self) -> None:
        self.assertFalse(_locale_is_de("pl-PL"))


class JoinFeaturesTests(SimpleTestCase):
    def test_empty_list_returns_empty_string(self) -> None:
        self.assertEqual(_join_features([], locale_de=True), "")

    def test_single_known_feature_de(self) -> None:
        result = _join_features(["ASYMMETRY"], locale_de=True)
        self.assertEqual(result, "Asymmetrie")

    def test_single_known_feature_en(self) -> None:
        result = _join_features(["ASYMMETRY"], locale_de=False)
        self.assertEqual(result, "Asymmetry")

    def test_unknown_feature_only_returns_empty(self) -> None:
        result = _join_features(["COMPLETELY_UNKNOWN"], locale_de=True)
        self.assertEqual(result, "")

    def test_two_features_de_joined_with_sowie(self) -> None:
        result = _join_features(["ASYMMETRY", "MULTICOLOR"], locale_de=True)
        self.assertIn("Asymmetrie", result)
        self.assertIn("sowie", result)

    def test_three_features_de_joined_with_comma_and_sowie(self) -> None:
        result = _join_features(["ASYMMETRY", "MULTICOLOR", "IRREGULAR_DOTS"], locale_de=True)
        self.assertIn(",", result)
        self.assertIn("sowie", result)

    def test_two_features_en_joined_with_and(self) -> None:
        result = _join_features(["ASYMMETRY", "MULTICOLOR"], locale_de=False)
        self.assertIn("and", result)


class FormatLesionNumbersTests(SimpleTestCase):
    def test_empty_returns_empty(self) -> None:
        self.assertEqual(_format_lesion_numbers([], locale_de=True), "")

    def test_single_number_de(self) -> None:
        self.assertEqual(_format_lesion_numbers([3], locale_de=True), "Nr. 3")

    def test_single_number_en(self) -> None:
        self.assertEqual(_format_lesion_numbers([3], locale_de=False), "no. 3")

    def test_numbers_sorted(self) -> None:
        result = _format_lesion_numbers([3, 1, 2], locale_de=True)
        self.assertEqual(result, "Nr. 1, 2, 3")


class GenerateBefundTextNoLesionsTests(SimpleTestCase):
    """Empty lesions list — only final_assessment summary."""

    def test_no_lesions_de_no_high_grade_suspicion(self) -> None:
        result = generate_befund_text(
            {"lesions": [], "final_assessment": "NO_HIGH_GRADE_SUSPICION"},
            authoring_locale="de-DE",
        )
        self.assertEqual(result["lesions"], [])
        self.assertIn("nicht", result["summary_generated_text"].lower())

    def test_no_lesions_en_no_high_grade_suspicion(self) -> None:
        result = generate_befund_text(
            {"lesions": [], "final_assessment": "NO_HIGH_GRADE_SUSPICION"},
            authoring_locale="en-US",
        )
        self.assertEqual(result["lesions"], [])
        self.assertIn("no high-grade", result["summary_generated_text"].lower())

    def test_no_lesions_de_high_grade_cannot_be_excluded(self) -> None:
        result = generate_befund_text(
            {"lesions": [], "final_assessment": "HIGH_GRADE_CANNOT_BE_EXCLUDED"},
            authoring_locale="de-DE",
        )
        self.assertIn("ausgeschlossen", result["summary_generated_text"])

    def test_no_lesions_unknown_final_assessment_gives_empty_summary(self) -> None:
        result = generate_befund_text(
            {"lesions": [], "final_assessment": "COMPLETELY_UNKNOWN"},
            authoring_locale="de-DE",
        )
        self.assertEqual(result["summary_generated_text"], "")

    def test_missing_lesions_key_treated_as_empty(self) -> None:
        result = generate_befund_text(
            {"final_assessment": "NO_HIGH_GRADE_SUSPICION"},
            authoring_locale="de-DE",
        )
        self.assertEqual(result["lesions"], [])


class GenerateBefundTextSingleLesionTests(SimpleTestCase):
    def _payload(self, locale: str = "de-DE") -> dict:
        return {
            "lesions": [
                {
                    "lesion_numbers": [1],
                    "dermatoscopic_features": ["ASYMMETRY", "IRREGULAR_BORDER"],
                    "clinical_assessment": "CONTROL_NEEDED",
                    "malignancy_risk": "LOW_SUSPICION",
                }
            ],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }

    def test_single_lesion_de_contains_german_label(self) -> None:
        result = generate_befund_text(self._payload(), authoring_locale="de-DE")
        self.assertEqual(len(result["lesions"]), 1)
        text = result["lesions"][0]["generated_text"]
        self.assertIn("Asymmetrie", text)
        self.assertIn("1", text)

    def test_single_lesion_en_contains_english_label(self) -> None:
        result = generate_befund_text(self._payload(), authoring_locale="en-US")
        text = result["lesions"][0]["generated_text"]
        self.assertIn("Asymmetry", text)

    def test_single_lesion_unknown_features_silently_dropped(self) -> None:
        payload = {
            "lesions": [
                {
                    "lesion_numbers": [2],
                    "dermatoscopic_features": ["UNKNOWN_FEAT", "ASYMMETRY"],
                    "clinical_assessment": "UNREMARKABLE",
                    "malignancy_risk": "NO_SUSPICION",
                }
            ],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        result = generate_befund_text(payload, authoring_locale="de-DE")
        self.assertIn("Asymmetrie", result["lesions"][0]["generated_text"])

    def test_single_lesion_unknown_clinical_assessment_shows_dash(self) -> None:
        payload = {
            "lesions": [
                {
                    "lesion_numbers": [1],
                    "dermatoscopic_features": [],
                    "clinical_assessment": "BOGUS_CODE",
                    "malignancy_risk": "NO_SUSPICION",
                }
            ],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        result = generate_befund_text(payload, authoring_locale="de-DE")
        self.assertIn("—", result["lesions"][0]["generated_text"])

    def test_lesion_no_backward_compat_single_int(self) -> None:
        """Legacy lesion_no (int) instead of lesion_numbers (list) is supported."""
        payload = {
            "lesions": [
                {
                    "lesion_no": 5,
                    "dermatoscopic_features": ["MULTICOLOR"],
                    "clinical_assessment": "SUSPICIOUS",
                    "malignancy_risk": "CANNOT_EXCLUDE",
                }
            ],
            "final_assessment": "HIGH_GRADE_CANNOT_BE_EXCLUDED",
        }
        result = generate_befund_text(payload, authoring_locale="de-DE")
        self.assertEqual(len(result["lesions"]), 1)
        self.assertEqual(result["lesions"][0]["lesion_numbers"], [5])


class GenerateBefundTextMultipleLesionsTests(SimpleTestCase):
    def _multi_payload(self) -> dict:
        return {
            "lesions": [
                {
                    "lesion_numbers": [1],
                    "dermatoscopic_features": ["ASYMMETRY"],
                    "clinical_assessment": "CONTROL_NEEDED",
                    "malignancy_risk": "LOW_SUSPICION",
                },
                {
                    "lesion_numbers": [2, 3],
                    "dermatoscopic_features": [],
                    "clinical_assessment": "SLIGHTLY_ATYPICAL",
                    "malignancy_risk": "NO_SUSPICION",
                },
            ],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }

    def test_multiple_lesions_returns_correct_count(self) -> None:
        result = generate_befund_text(self._multi_payload(), authoring_locale="de-DE")
        self.assertEqual(len(result["lesions"]), 2)

    def test_multiple_lesions_summary_de_mentions_all_groups(self) -> None:
        result = generate_befund_text(self._multi_payload(), authoring_locale="de-DE")
        summary = result["summary_generated_text"]
        self.assertIn("1", summary)
        self.assertIn("2", summary)

    def test_multiple_lesions_summary_en_mentions_all_groups(self) -> None:
        result = generate_befund_text(self._multi_payload(), authoring_locale="en-US")
        summary = result["summary_generated_text"]
        self.assertIn("1", summary)
        self.assertIn("2", summary)

    def test_suspicious_lesion_in_summary_de(self) -> None:
        payload = {
            "lesions": [
                {
                    "lesion_numbers": [1],
                    "dermatoscopic_features": [],
                    "clinical_assessment": "SUSPICIOUS",
                    "malignancy_risk": "CANNOT_EXCLUDE",
                }
            ],
            "final_assessment": "HIGH_GRADE_CANNOT_BE_EXCLUDED",
        }
        result = generate_befund_text(payload, authoring_locale="de-DE")
        self.assertIn("suspekt", result["summary_generated_text"].lower())


class GenerateBefundTextTemplatBodyTests(SimpleTestCase):
    def test_template_body_prepended_to_summary(self) -> None:
        result = generate_befund_text(
            {"lesions": [], "final_assessment": "NO_HIGH_GRADE_SUSPICION"},
            authoring_locale="de-DE",
            template_body="Individuelle Vorlage.",
        )
        self.assertTrue(result["summary_generated_text"].startswith("Individuelle Vorlage."))

    def test_empty_template_body_not_prepended(self) -> None:
        result_no_tpl = generate_befund_text(
            {"lesions": [], "final_assessment": "NO_HIGH_GRADE_SUSPICION"},
            authoring_locale="de-DE",
            template_body="   ",
        )
        result_tpl = generate_befund_text(
            {"lesions": [], "final_assessment": "NO_HIGH_GRADE_SUSPICION"},
            authoring_locale="de-DE",
        )
        self.assertEqual(result_no_tpl["summary_generated_text"], result_tpl["summary_generated_text"])

    def test_template_body_separated_by_blank_line(self) -> None:
        result = generate_befund_text(
            {"lesions": [], "final_assessment": "NO_HIGH_GRADE_SUSPICION"},
            authoring_locale="de-DE",
            template_body="Header",
        )
        self.assertIn("\n\n", result["summary_generated_text"])
