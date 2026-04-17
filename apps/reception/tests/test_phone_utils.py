"""Unit tests for phone_utils.normalize_phone."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.reception.phone_utils import format_phone_e164_for_sms, normalize_phone


class NormalizePhoneTests(SimpleTestCase):
    def test_strips_non_digits(self) -> None:
        self.assertEqual(normalize_phone("+49 176 22 22 222"), "491762222222")

    def test_strips_leading_zero_national_trunk(self) -> None:
        self.assertEqual(normalize_phone("0176-2222222"), "1762222222")

    def test_strips_international_00_prefix(self) -> None:
        self.assertEqual(normalize_phone("0049 176 2222222"), "491762222222")

    def test_no_extra_strip_when_already_e164_digits(self) -> None:
        self.assertEqual(normalize_phone("491762222222"), "491762222222")

    def test_all_zeros_or_only_separators_returns_empty(self) -> None:
        self.assertEqual(normalize_phone("000"), "")
        self.assertEqual(normalize_phone("0-0-0"), "")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(normalize_phone(""), "")
        self.assertEqual(normalize_phone("  -  "), "")

    def test_too_short_after_strip_returns_empty(self) -> None:
        self.assertEqual(normalize_phone("012345"), "")


class FormatPhoneE164ForSmsTests(SimpleTestCase):
    def test_polish_stored_with_48(self) -> None:
        self.assertEqual(format_phone_e164_for_sms("48500111222"), "+48500111222")
        self.assertEqual(format_phone_e164_for_sms("+48 500 111 222"), "+48500111222")

    def test_german_national_gets_49_prefix(self) -> None:
        self.assertEqual(format_phone_e164_for_sms("1762222222"), "+491762222222")

    def test_german_full_international_unchanged(self) -> None:
        self.assertEqual(format_phone_e164_for_sms("491762222222"), "+491762222222")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(format_phone_e164_for_sms(""), "")
        self.assertEqual(format_phone_e164_for_sms("   "), "")
