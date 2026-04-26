"""SMSAPI phone formatting tests (no DB)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.integrations.sms.client import format_phone_for_smsapi


class FormatPhoneForSmsApiTests(SimpleTestCase):
    """format_phone_for_smsapi matches E.164 rules for SMS dispatch."""

    def test_polish_plus_48(self) -> None:
        self.assertEqual(format_phone_for_smsapi("48500111222"), "+48500111222")

    def test_german_prepends_49(self) -> None:
        self.assertEqual(format_phone_for_smsapi("1761234567"), "+491761234567")

    def test_german_already_has_49(self) -> None:
        self.assertEqual(format_phone_for_smsapi("491761234567"), "+491761234567")

    def test_french_international_digits(self) -> None:
        self.assertEqual(
            format_phone_for_smsapi("33123456789"),
            "+33123456789",
        )

    def test_ukrainian_international_digits(self) -> None:
        self.assertEqual(
            format_phone_for_smsapi("380311234567"),
            "+380311234567",
        )

    def test_czech_international_digits(self) -> None:
        self.assertEqual(
            format_phone_for_smsapi("420212345678"),
            "+420212345678",
        )

    def test_swiss_international_digits(self) -> None:
        self.assertEqual(
            format_phone_for_smsapi("41212345678"),
            "+41212345678",
        )

    def test_french_national_with_default_region_kwarg(self) -> None:
        self.assertEqual(
            format_phone_for_smsapi("612345678", default_region="FR"),
            "+33612345678",
        )
