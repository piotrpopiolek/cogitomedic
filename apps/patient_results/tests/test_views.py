"""Smoke tests for ergebnisse (patient results) HTML views.

Covers: ergebnisse_login_view, ergebnisse_otp_view,
ergebnisse_documents_view.
Focuses on status codes and session-based redirects.
"""

from __future__ import annotations

from django.test import Client, TestCase

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
