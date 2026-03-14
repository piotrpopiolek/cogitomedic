"""Tests for SMS adapter and patient results text."""
from __future__ import annotations

from django.test import TestCase

from apps.integrations.sms.client import get_sms_patient_results_text


class GetSmsPatientResultsTextTests(TestCase):
    """Test get_sms_patient_results_text with DB translations."""

    def test_returns_german_text_when_de_locale(self) -> None:
        result = get_sms_patient_results_text("de-DE", "https://example.com/xyz")
        self.assertIn("Neue Dokumentation", result)
        self.assertIn("https://example.com/xyz", result)

    def test_returns_english_text_when_en_locale(self) -> None:
        result = get_sms_patient_results_text("en-GB", "https://example.com/abc")
        self.assertIn("New documentation", result)
        self.assertIn("https://example.com/abc", result)

    def test_returns_polish_text_when_pl_locale(self) -> None:
        result = get_sms_patient_results_text("pl-PL", "https://example.com/def")
        self.assertIn("Nowa dokumentacja", result)
        self.assertIn("https://example.com/def", result)

    def test_fallback_when_none_locale(self) -> None:
        result = get_sms_patient_results_text(None, "https://fallback.url")
        self.assertIn("Dokumentation", result)  # DE default
        self.assertIn("https://fallback.url", result)
