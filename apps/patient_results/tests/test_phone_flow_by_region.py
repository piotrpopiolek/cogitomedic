"""
End-to-end: Patient.phone normalization → OTP request/verify → documents list.

Uses 25 mobile numbers per region from reception test fixtures (same as phone_utils tests).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings

from apps.patient_results.models import PatientResultsOtpSession
from apps.reception.models import Patient
from apps.reception.phone_utils import (
    SUPPORTED_SMS_REGIONS,
    infer_sms_region_from_phone,
    normalize_phone_for_patient_storage,
)
from apps.reception.tests.phone_fixtures import load_mobile_numbers_by_region

_FIXED_OTP = 654321
_TEST_PEPPER = "test-pepper-flow"
_TEST_DOB = date(1985, 6, 15)


@override_settings(
    CAPTCHA_VERIFY_SKIP=True,
    PATIENT_RESULTS_OTP_PEPPER=_TEST_PEPPER,
    RATELIMIT_ENABLE=False,
)
class PatientResultsPhoneFlowByRegionTests(TestCase):
    """Reception save → portal OTP (alternate format) → verify → GET documents."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.fixtures = load_mobile_numbers_by_region()
        cls.client = Client()

    def _portal_request_phone(self, case: dict) -> str:
        if case["supports_national_roundtrip"]:
            return case["national"]
        return case["international_digits"]

    def _portal_verify_phone(self, case: dict) -> str:
        return case["e164"]

    @patch(
        "apps.patient_results.services.random.randint",
        return_value=_FIXED_OTP,
    )
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_full_flow_all_supported_regions(
        self, mock_get_adapter: MagicMock, _mock_randint: MagicMock
    ) -> None:
        mock_adapter = mock_get_adapter.return_value
        mock_adapter.send_sms = MagicMock()

        for region in SUPPORTED_SMS_REGIONS:
            for index, case in enumerate(self.fixtures[region]):
                with self.subTest(region=region, index=index, e164=case["e164"]):
                    self._run_single_flow(case, mock_adapter)

    def _run_single_flow(self, case: dict, mock_adapter: MagicMock) -> None:
        mock_adapter.send_sms.reset_mock()
        PatientResultsOtpSession.objects.all().delete()
        Patient.objects.filter(email__startswith="flow-").delete()

        region = case["region"]
        e164 = case["e164"]
        email = f"flow-{region}-{case['international_digits']}@example.test"

        patient = Patient.objects.create(
            first_name="Flow",
            last_name=region,
            date_of_birth=_TEST_DOB,
            phone=e164,
            email=email,
            doctolib_patient_id=None,
        )
        patient.refresh_from_db()

        expected_stored = normalize_phone_for_patient_storage(e164)
        self.assertEqual(patient.phone, expected_stored)
        self.assertEqual(infer_sms_region_from_phone(patient.phone), region)

        request_phone = self._portal_request_phone(case)
        verify_phone = self._portal_verify_phone(case)
        dob_str = _TEST_DOB.isoformat()

        otp_req = self.client.post(
            "/api/v1/patient-results/request-otp",
            data={
                "phone": request_phone,
                "date_of_birth": dob_str,
                "captcha_token": "skip",
            },
            content_type="application/json",
        )
        self.assertEqual(otp_req.status_code, 200, otp_req.content)
        self.assertEqual(otp_req.json(), {"status": "ok"})
        session = PatientResultsOtpSession.objects.get(patient=patient)
        self.assertEqual(session.phone, patient.phone)
        mock_adapter.send_sms.assert_called_once()
        sms_kwargs = mock_adapter.send_sms.call_args.kwargs
        self.assertEqual(sms_kwargs["default_region"], region)
        self.assertEqual(sms_kwargs["to"], patient.phone)

        verify_resp = self.client.post(
            "/api/v1/patient-results/verify-otp",
            data={
                "phone": verify_phone,
                "date_of_birth": dob_str,
                "otp_code": str(_FIXED_OTP),
            },
            content_type="application/json",
        )
        self.assertEqual(verify_resp.status_code, 200, verify_resp.content)
        self.assertIn("sessionid", self.client.cookies)
        session.refresh_from_db()
        self.assertIsNotNone(session.verified_at)

        docs_resp = self.client.get("/api/v1/patient-results/documents")
        self.assertEqual(docs_resp.status_code, 200, docs_resp.content)
        self.assertIn("items", docs_resp.json())
