"""Regression: 25 mobile numbers per SUPPORTED_SMS_REGIONS (phone_utils contract)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.reception.phone_test_numbers import MOBILE_NUMBERS_PER_REGION, MobilePhoneCase
from apps.reception.phone_utils import (
    SUPPORTED_SMS_REGIONS,
    format_phone_e164_for_sms,
    infer_sms_region_from_phone,
    normalize_phone_for_patient_storage,
    phone_lookup_variants,
)
from apps.reception.tests.phone_fixtures import load_mobile_numbers_by_region


def _assert_e164_contract(
    testcase: SimpleTestCase,
    case: MobilePhoneCase,
    *,
    input_phone: str,
    label: str,
) -> None:
    region = case["region"]
    e164 = case["e164"]
    stored = normalize_phone_for_patient_storage(input_phone)
    with testcase.subTest(region=region, e164=e164, input=label):
        testcase.assertTrue(stored, msg="empty stored")
        testcase.assertEqual(infer_sms_region_from_phone(stored), region)
        testcase.assertEqual(format_phone_e164_for_sms(stored), e164)
        testcase.assertIn(stored, phone_lookup_variants(input_phone))


class MobileNumbersFixtureTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.fixtures = load_mobile_numbers_by_region()

    def test_fixture_covers_all_supported_regions(self) -> None:
        self.assertEqual(set(self.fixtures.keys()), set(SUPPORTED_SMS_REGIONS))
        for region in SUPPORTED_SMS_REGIONS:
            with self.subTest(region=region):
                self.assertEqual(
                    len(self.fixtures[region]),
                    MOBILE_NUMBERS_PER_REGION,
                )

    def test_mobile_e164_round_trip_per_region(self) -> None:
        for region in SUPPORTED_SMS_REGIONS:
            for index, case in enumerate(self.fixtures[region]):
                with self.subTest(region=region, index=index, e164=case["e164"]):
                    _assert_e164_contract(
                        self, case, input_phone=case["e164"], label="e164"
                    )
                    _assert_e164_contract(
                        self,
                        case,
                        input_phone=case["international_digits"],
                        label="digits",
                    )

    def test_mobile_national_round_trip_when_supported(self) -> None:
        for region in SUPPORTED_SMS_REGIONS:
            for index, case in enumerate(self.fixtures[region]):
                if not case["supports_national_roundtrip"]:
                    continue
                with self.subTest(region=region, index=index, e164=case["e164"]):
                    _assert_e164_contract(
                        self, case, input_phone=case["national"], label="national"
                    )
                    stored = normalize_phone_for_patient_storage(case["national"])
                    stored_e164 = normalize_phone_for_patient_storage(case["e164"])
                    self.assertEqual(stored, stored_e164)
