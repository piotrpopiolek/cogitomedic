"""Tests for patient_results services."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.patient_results.constants import OTP_RATE_LIMIT_PER_HOUR
from apps.patient_results.models import PatientResultsOtpSession
from apps.patient_results.services import request_otp, verify_otp
import phonenumbers

from apps.reception.phone_utils import infer_sms_region_from_phone
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    QueueEntry,
    QueueStatus,
)
from apps.users.models import StaffUser


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
        self.assertEqual(session.phone, "1762222222")
        self.assertIsNone(session.verified_at)
        mock_adapter.send_sms.assert_called_once()
        call_args = mock_adapter.send_sms.call_args
        self.assertIn("1762222222", str(call_args))
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


class RequestOtpUkTests(TestCase):
    def setUp(self) -> None:
        ex = phonenumbers.example_number("GB")
        assert ex is not None
        self.gb_e164 = phonenumbers.format_number(
            ex, phonenumbers.PhoneNumberFormat.E164
        )
        self.gb_national = phonenumbers.format_number(
            ex, phonenumbers.PhoneNumberFormat.NATIONAL
        )
        self.patient = Patient.objects.create(
            first_name="UK",
            last_name="Patient",
            date_of_birth=date(1988, 7, 7),
            phone=self.gb_e164,
            email="uk@example.com",
            country_code="DE",
            doctolib_patient_id=None,
        )
        self.patient.refresh_from_db()
        self.assertEqual(infer_sms_region_from_phone(self.patient.phone), "GB")

    @override_settings(
        CAPTCHA_VERIFY_SKIP=True, PATIENT_RESULTS_OTP_PEPPER="test-pepper"
    )
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_request_otp_uk_national_format(self, mock_get_adapter) -> None:
        mock_adapter = mock_get_adapter.return_value
        result = request_otp(
            phone=self.gb_national,
            date_of_birth=date(1988, 7, 7),
            captcha_token="skip",
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.audit_outcome, "sms_sent")
        mock_adapter.send_sms.assert_called_once()
        self.assertEqual(mock_adapter.send_sms.call_args.kwargs["default_region"], "GB")

    @override_settings(
        CAPTCHA_VERIFY_SKIP=True, PATIENT_RESULTS_OTP_PEPPER="test-pepper"
    )
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_verify_otp_uk_national_format(self, mock_get_adapter) -> None:
        mock_get_adapter.return_value.send_sms = lambda *a, **k: None
        request_otp(
            phone=self.gb_national,
            date_of_birth=date(1988, 7, 7),
            captcha_token="skip",
        )
        session = PatientResultsOtpSession.objects.get(patient=self.patient)
        otp = "654321"
        pepper = "test-pepper"
        session.otp_code_hash = hashlib.sha256(f"{pepper}{otp}".encode()).hexdigest()
        session.save(update_fields=["otp_code_hash"])
        result = verify_otp(
            phone=self.gb_national,
            date_of_birth=date(1988, 7, 7),
            otp_code=otp,
        )
        self.assertTrue(result.success)

    @override_settings(
        CAPTCHA_VERIFY_SKIP=True, PATIENT_RESULTS_OTP_PEPPER="test-pepper"
    )
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_request_otp_rate_limit_shared_across_phone_formats(
        self, mock_get_adapter
    ) -> None:
        """Legacy phone_norm vs stored 44… must not bypass OTP_RATE_LIMIT_PER_HOUR."""
        mock_adapter = mock_get_adapter.return_value
        mock_adapter.send_sms = MagicMock()
        dob = date(1988, 7, 7)
        for _ in range(OTP_RATE_LIMIT_PER_HOUR):
            request_otp(
                phone=self.gb_national,
                date_of_birth=dob,
                captcha_token="skip",
            )
        self.assertEqual(
            PatientResultsOtpSession.objects.filter(patient=self.patient).count(),
            OTP_RATE_LIMIT_PER_HOUR,
        )
        self.assertEqual(mock_adapter.send_sms.call_count, OTP_RATE_LIMIT_PER_HOUR)
        result = request_otp(
            phone=self.gb_e164,
            date_of_birth=dob,
            captcha_token="skip",
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.audit_outcome, "silent_no_op")
        self.assertEqual(
            PatientResultsOtpSession.objects.filter(patient=self.patient).count(),
            OTP_RATE_LIMIT_PER_HOUR,
        )
        self.assertEqual(mock_adapter.send_sms.call_count, OTP_RATE_LIMIT_PER_HOUR)


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
                phone=self.patient.phone,
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
