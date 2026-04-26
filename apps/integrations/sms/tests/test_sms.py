"""Tests for SMS adapter and patient results text."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

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


@override_settings(SMSAPI_USE_MOCK=False, SMSAPI_ACCESS_TOKEN="test-token")
class SmsApiAdapterSendSmsTests(SimpleTestCase):
    @patch("smsapi.client.SmsApiPlClient")
    def test_real_adapter_send_sms_calls_smsapi_with_e164(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.sms.send.return_value = MagicMock(id="msg-1", status="QUEUED")
        mock_client_cls.return_value = mock_client

        from apps.integrations.sms.client import _SmsApiAdapter

        adapter = _SmsApiAdapter()
        adapter.send_sms("1761234567", "Hello", default_region="DE")

        mock_client.sms.send.assert_called_once()
        call_kw = mock_client.sms.send.call_args.kwargs
        self.assertTrue(call_kw["to"].startswith("+49"))
        self.assertEqual(call_kw["message"], "Hello")
