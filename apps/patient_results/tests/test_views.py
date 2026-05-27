"""Smoke tests for ergebnisse (patient results) HTML views.

Covers: ergebnisse_login_view, ergebnisse_otp_view,
ergebnisse_documents_view.
Focuses on status codes and session-based redirects.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.patient_results.models import PatientResultsOtpSession
from apps.reception.models import Patient

LOGIN_URL = "/"
OTP_URL = "/otp/"
DOCUMENTS_URL = "/documents/"


class ErgebnisseViewSmokeTests(TestCase):
    def setUp(self):
        self.client = Client()

    # -- login page --------------------------------------------------------

    def test_login_page_returns_200(self):
        resp = self.client.get(LOGIN_URL)
        self.assertEqual(resp.status_code, 200)

    def test_login_page_with_pl_locale_returns_200(self):
        resp = self.client.get(
            LOGIN_URL,
            HTTP_ACCEPT_LANGUAGE="pl",
        )
        self.assertEqual(resp.status_code, 200)

    def test_login_post_invalid_data_stays_on_page(self):
        resp = self.client.post(
            LOGIN_URL,
            {"phone": "", "date_of_birth": ""},
        )
        self.assertEqual(resp.status_code, 200)

    # -- otp page ----------------------------------------------------------

    def test_otp_without_session_redirects_to_login(self):
        resp = self.client.get(OTP_URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/", resp.url)

    # -- documents page ----------------------------------------------------

    def test_documents_without_session_redirects_to_login(
        self,
    ):
        resp = self.client.get(DOCUMENTS_URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/", resp.url)


@override_settings(CAPTCHA_VERIFY_SKIP=True, PATIENT_RESULTS_OTP_PEPPER="test-pepper")
class ErgebnisseLoginPostTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.phone = "01761237788"
        self.dob = date(1992, 3, 20)

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_login_post_success_redirects_to_otp(self, mock_get_adapter) -> None:
        mock_get_adapter.return_value.send_sms = lambda *a, **k: None
        Patient.objects.create(
            first_name="Html",
            last_name="Patient",
            date_of_birth=self.dob,
            phone=self.phone,
            email="html@example.com",
        )
        response = self.client.post(
            LOGIN_URL,
            {
                "phone": self.phone,
                "date_of_birth": self.dob.isoformat(),
                "captcha_token": "skip",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["ergebnisse_phone"], self.phone)
        self.assertEqual(self.client.session["ergebnisse_dob"], self.dob.isoformat())
        self.assertNotIn("ergebnisse_last_name", self.client.session)

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_login_post_needs_last_name_for_shared_phone(
        self, mock_get_adapter
    ) -> None:
        mock_get_adapter.return_value.send_sms = lambda *a, **k: None
        twin_dob = date(2010, 8, 8)
        Patient.objects.create(
            first_name="Anna",
            last_name="Schmidt",
            date_of_birth=twin_dob,
            phone=self.phone,
            email="anna.html@example.com",
        )
        Patient.objects.create(
            first_name="Eva",
            last_name="Weber",
            date_of_birth=twin_dob,
            phone=self.phone,
            email="eva.html@example.com",
        )
        response = self.client.post(
            LOGIN_URL,
            {
                "phone": self.phone,
                "date_of_birth": twin_dob.isoformat(),
                "captcha_token": "skip",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nachnamen")
        self.assertEqual(self.client.session.get("ergebnisse_phone"), None)

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_login_post_ambiguous_with_wrong_last_name_shows_error(
        self, mock_get_adapter
    ) -> None:
        mock_get_adapter.return_value.send_sms = lambda *a, **k: None
        twin_dob = date(2010, 9, 9)
        Patient.objects.create(
            first_name="Anna",
            last_name="Schmidt",
            date_of_birth=twin_dob,
            phone=self.phone,
            email="anna2.html@example.com",
        )
        Patient.objects.create(
            first_name="Eva",
            last_name="Weber",
            date_of_birth=twin_dob,
            phone=self.phone,
            email="eva2.html@example.com",
        )
        response = self.client.post(
            LOGIN_URL,
            {
                "phone": self.phone,
                "date_of_birth": twin_dob.isoformat(),
                "captcha_token": "skip",
                "last_name": "Wrong",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nachnamen")

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_login_post_with_last_name_stores_session_last_name(
        self, mock_get_adapter
    ) -> None:
        mock_get_adapter.return_value.send_sms = lambda *a, **k: None
        twin_dob = date(2010, 10, 10)
        Patient.objects.create(
            first_name="Anna",
            last_name="Schmidt",
            date_of_birth=twin_dob,
            phone=self.phone,
            email="anna3.html@example.com",
        )
        Patient.objects.create(
            first_name="Eva",
            last_name="Weber",
            date_of_birth=twin_dob,
            phone=self.phone,
            email="eva3.html@example.com",
        )
        response = self.client.post(
            LOGIN_URL,
            {
                "phone": self.phone,
                "date_of_birth": twin_dob.isoformat(),
                "captcha_token": "skip",
                "last_name": "Schmidt",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["ergebnisse_last_name"], "Schmidt")

    @override_settings(CAPTCHA_VERIFY_SKIP=False)
    def test_login_post_captcha_failure_stays_on_page(self) -> None:
        Patient.objects.create(
            first_name="Cap",
            last_name="Tcha",
            date_of_birth=self.dob,
            phone=self.phone,
            email="cap@example.com",
        )
        response = self.client.post(
            LOGIN_URL,
            {
                "phone": self.phone,
                "date_of_birth": self.dob.isoformat(),
                "captcha_token": "bad",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("ergebnisse_phone", self.client.session)


@override_settings(CAPTCHA_VERIFY_SKIP=True, PATIENT_RESULTS_OTP_PEPPER="test-pepper")
class ErgebnisseOtpPostTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.phone = "01764445566"
        self.dob = date(1985, 4, 4)
        self.patient = Patient.objects.create(
            first_name="Otp",
            last_name="Html",
            date_of_birth=self.dob,
            phone=self.phone,
            email="otp.html@example.com",
        )

    def _prime_login_session(self, *, last_name: str | None = None) -> None:
        session = self.client.session
        session["ergebnisse_phone"] = self.phone
        session["ergebnisse_dob"] = self.dob.isoformat()
        if last_name:
            session["ergebnisse_last_name"] = last_name
        session.save()

    def test_otp_post_empty_code_stays_on_page(self) -> None:
        self._prime_login_session()
        response = self.client.post(OTP_URL, {"otp_code": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="error"')

    @patch("apps.patient_results.services.get_sms_adapter")
    def test_otp_post_success_clears_staging_session(self, mock_get_adapter) -> None:
        mock_get_adapter.return_value.send_sms = lambda *a, **k: None
        self._prime_login_session(last_name="Html")
        otp = "778899"
        session = PatientResultsOtpSession.objects.create(
            patient=self.patient,
            phone=self.phone,
            otp_code_hash=hashlib.sha256(f"test-pepper{otp}".encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        self.assertIsNotNone(session.id)
        response = self.client.post(OTP_URL, {"otp_code": otp})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/documents/", response.url)
        self.assertNotIn("ergebnisse_phone", self.client.session)
        self.assertNotIn("ergebnisse_last_name", self.client.session)
