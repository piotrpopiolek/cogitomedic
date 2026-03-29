"""Tests for patient_results services."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.patient_results.models import PatientResultsOtpSession
from apps.patient_results.services import request_otp, verify_otp
from apps.reception.phone_utils import normalize_phone
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    QueueEntry,
    QueueStatus,
)
from apps.users.models import StaffUser


class NormalizePhoneTests(TestCase):
    def test_strips_non_digits(self) -> None:
        self.assertEqual(normalize_phone("+49 176 22 22 222"), "491762222222")
        self.assertEqual(normalize_phone("0176-2222222"), "01762222222")

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(normalize_phone(""), "")
        self.assertEqual(normalize_phone("  -  "), "")


class RequestOtpTests(TestCase):
    def setUp(self) -> None:
        self.patient = Patient.objects.create(
            first_name="Test",
            last_name="Patient",
            date_of_birth=date(1990, 5, 15),
            phone="01762222222",
            email="test@example.com",
            doctolib_patient_id=None,
        )
        self.reception_user = StaffUser.objects.create_user(
            username="reception-pr",
            email="reception@example.com",
            password="x",
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="HAM", name="Hamburg")
        room = ConsultingRoom.objects.create(
            clinic_site=clinic, code="R1", name="Room 1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=self.patient,
            entry_status="WAITING",
            position_no=1,
            created_by_user=self.reception_user,
        )

    @override_settings(CAPTCHA_VERIFY_SKIP=True)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_request_otp_creates_session_and_sends_sms(self, mock_get_adapter) -> None:
        mock_adapter = mock_get_adapter.return_value
        result = request_otp(
            phone="01762222222",
            date_of_birth=date(1990, 5, 15),
            captcha_token="skip",
        )
        self.assertEqual(result.status, "ok")
        session = PatientResultsOtpSession.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(session)
        self.assertEqual(session.phone, "01762222222")
        self.assertIsNone(session.verified_at)
        mock_adapter.send_sms.assert_called_once()
        call_args = mock_adapter.send_sms.call_args
        self.assertIn("01762222222", str(call_args))
        self.assertRegex(call_args[1]["message"], r"\d{6}")

    @override_settings(CAPTCHA_VERIFY_SKIP=False)
    def test_request_otp_fails_without_captcha(self) -> None:
        result = request_otp(
            phone="01762222222",
            date_of_birth=date(1990, 5, 15),
            captcha_token="",
        )
        self.assertEqual(result.status, "captcha_failed")
        self.assertEqual(PatientResultsOtpSession.objects.count(), 0)

    @override_settings(CAPTCHA_VERIFY_SKIP=True)
    def test_request_otp_no_patient_returns_ok_no_session(self) -> None:
        result = request_otp(
            phone="+49999999999",
            date_of_birth=date(1990, 5, 15),
            captcha_token="skip",
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(PatientResultsOtpSession.objects.count(), 0)

    @override_settings(
        CAPTCHA_VERIFY_SKIP=True, ENVIRONMENT="staging", PATIENT_RESULTS_OTP_PEPPER=""
    )
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_request_otp_requires_pepper_outside_dev_environment(
        self, mock_get_adapter
    ) -> None:
        with self.assertRaises(ValueError):
            request_otp(
                phone="01762222222",
                date_of_birth=date(1990, 5, 15),
                captcha_token="skip",
            )
        mock_get_adapter.return_value.send_sms.assert_not_called()


class VerifyOtpTests(TestCase):
    def setUp(self) -> None:
        self.patient = Patient.objects.create(
            first_name="Verify",
            last_name="Patient",
            date_of_birth=date(1985, 3, 20),
            phone="01761111111",
            email="verify@example.com",
            doctolib_patient_id=None,
        )

    def _create_session_with_otp(self, otp: str) -> PatientResultsOtpSession:
        pepper = "test-pepper"
        payload = f"{pepper}{otp}"
        h = hashlib.sha256(payload.encode()).hexdigest()
        with patch.dict(
            "django.conf.settings.__dict__",
            {"PATIENT_RESULTS_OTP_PEPPER": "test-pepper"},
        ):
            return PatientResultsOtpSession.objects.create(
                patient=self.patient,
                phone="01761111111",
                otp_code_hash=h,
                expires_at=timezone.now() + timedelta(minutes=15),
            )

    @override_settings(PATIENT_RESULTS_OTP_PEPPER="test-pepper")
    def test_verify_otp_success(self) -> None:
        otp = "123456"
        self._create_session_with_otp(otp)
        result = verify_otp(
            phone="01761111111",
            date_of_birth=date(1985, 3, 20),
            otp_code=otp,
        )
        self.assertTrue(result.success)
        self.assertEqual(str(result.patient_id), str(self.patient.id))
        session = PatientResultsOtpSession.objects.get(patient=self.patient)
        self.assertIsNotNone(session.verified_at)

    @override_settings(PATIENT_RESULTS_OTP_PEPPER="test-pepper")
    def test_verify_otp_wrong_code_fails(self) -> None:
        self._create_session_with_otp("123456")
        result = verify_otp(
            phone="01761111111",
            date_of_birth=date(1985, 3, 20),
            otp_code="999999",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "invalid")

    @override_settings(PATIENT_RESULTS_OTP_PEPPER="test-pepper")
    def test_verify_otp_no_matching_session_fails(self) -> None:
        # No session for this phone/DOB
        result = verify_otp(
            phone="01999999999",
            date_of_birth=date(1985, 3, 20),
            otp_code="123456",
        )
        self.assertFalse(result.success)
