"""Unit tests for phone_utils.normalize_phone and format_phone_e164_for_sms."""

from __future__ import annotations

import phonenumbers
from django.test import SimpleTestCase

from apps.reception.phone_utils import (
    SUPPORTED_SMS_REGIONS,
    format_phone_e164_for_sms,
    normalize_phone,
)


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


class NormalizePhoneWithDefaultRegionTests(SimpleTestCase):
    def test_fr_national_input_stores_international_digits(self) -> None:
        self.assertEqual(
            normalize_phone("01 23 45 67 89", default_region="FR"),
            "33123456789",
        )


class FormatPhoneE164ForSmsTests(SimpleTestCase):
    def test_polish_stored_with_48(self) -> None:
        self.assertEqual(format_phone_e164_for_sms("48500111222"), "+48500111222")
        self.assertEqual(format_phone_e164_for_sms("+48 500 111 222"), "+48500111222")

    def test_german_national_gets_49_prefix(self) -> None:
        self.assertEqual(format_phone_e164_for_sms("1762222222"), "+491762222222")

    def test_german_full_international_unchanged(self) -> None:
        self.assertEqual(format_phone_e164_for_sms("491762222222"), "+491762222222")

    def test_french_national_digits_with_default_region(self) -> None:
        self.assertEqual(
            format_phone_e164_for_sms("612345678", default_region="FR"),
            "+33612345678",
        )

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(format_phone_e164_for_sms(""), "")
        self.assertEqual(format_phone_e164_for_sms("   "), "")


class FormatPhoneSupportedSmsRegionsTests(SimpleTestCase):
    def test_each_supported_region_example_stored_digits_to_e164(self) -> None:
        for region in SUPPORTED_SMS_REGIONS:
            with self.subTest(region=region):
                ex = phonenumbers.example_number(region)
                self.assertIsNotNone(ex, msg=region)
                e164 = phonenumbers.format_number(
                    ex, phonenumbers.PhoneNumberFormat.E164
                )
                stored = e164.lstrip("+")
                self.assertEqual(
                    format_phone_e164_for_sms(stored, default_region="DE"),
                    e164,
                )
