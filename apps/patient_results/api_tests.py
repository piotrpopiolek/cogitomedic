"""API tests for patient results portal."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.patient_results.models import PatientResultsOtpSession
from apps.reception.models import ClinicSite, ConsultingRoom, DailyQueue, Patient, QueueEntry, QueueEntryStatus, QueueStatus
from apps.users.models import StaffUser


class PatientResultsRequestOtpApiTests(TestCase):
    def setUp(self) -> None:
        self.patient = Patient.objects.create(
            first_name="Api",
            last_name="Patient",
            date_of_birth=date(1990, 1, 15),
            phone="01763333333",
            email="api@example.com",
            doctolib_patient_id=None,
        )
        self.reception_user = StaffUser.objects.create_user(
            username="reception-api",
            email="reception.api@example.com",
            password="x",
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="BER", name="Berlin")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="Room 1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=self.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            created_by_user=self.reception_user,
        )

    @override_settings(CAPTCHA_VERIFY_SKIP=True)
    @patch("apps.patient_results.services.get_sms_adapter")
    def test_request_otp_success(self, mock_get_adapter) -> None:
        mock_get_adapter.return_value.send_sms = lambda *a, **k: None
        response = self.client.post(
            "/api/v1/patient-results/request-otp",
            data={"phone": "01763333333", "date_of_birth": "1990-01-15", "captcha_token": "skip"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertTrue(PatientResultsOtpSession.objects.filter(patient=self.patient).exists())

    @override_settings(CAPTCHA_VERIFY_SKIP=False)
    def test_request_otp_captcha_fail(self) -> None:
        response = self.client.post(
            "/api/v1/patient-results/request-otp",
            data={"phone": "01763333333", "date_of_birth": "1990-01-15", "captcha_token": ""},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class PatientResultsVerifyOtpApiTests(TestCase):
    def setUp(self) -> None:
        self.patient = Patient.objects.create(
            first_name="Verify",
            last_name="Api",
            date_of_birth=date(1988, 7, 20),
            phone="01764444444",
            email="verify.api@example.com",
            doctolib_patient_id=None,
        )

    @override_settings(PATIENT_RESULTS_OTP_PEPPER="test-pepper")
    def _create_session(self, otp: str) -> None:
        import hashlib
        h = hashlib.sha256(f"test-pepper{otp}".encode()).hexdigest()
        PatientResultsOtpSession.objects.create(
            patient=self.patient,
            phone="01764444444",
            otp_code_hash=h,
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    @override_settings(PATIENT_RESULTS_OTP_PEPPER="test-pepper")
    def test_verify_otp_success_sets_session(self) -> None:
        self._create_session("654321")
        response = self.client.post(
            "/api/v1/patient-results/verify-otp",
            data={"phone": "01764444444", "date_of_birth": "1988-07-20", "otp_code": "654321"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sessionid", self.client.cookies)

        docs_response = self.client.get("/api/v1/patient-results/documents")
        self.assertEqual(docs_response.status_code, 200)


class PatientResultsDocumentsApiTests(TestCase):
    def setUp(self) -> None:
        self.patient = Patient.objects.create(
            first_name="Docs",
            last_name="Patient",
            date_of_birth=date(1992, 3, 10),
            phone="01765555555",
            email="docs@example.com",
            doctolib_patient_id=None,
        )

    def test_documents_requires_session(self) -> None:
        response = self.client.get("/api/v1/patient-results/documents")
        self.assertEqual(response.status_code, 401)

    def test_documents_with_session_returns_list(self) -> None:
        session = self.client.session
        session["patient_results_patient_id"] = str(self.patient.id)
        session.save()
        response = self.client.get("/api/v1/patient-results/documents")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)
