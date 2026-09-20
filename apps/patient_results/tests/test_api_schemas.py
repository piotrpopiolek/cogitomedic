"""Unit tests for patient-results Pydantic request bodies."""

from __future__ import annotations

from datetime import date, timedelta

from django.test import SimpleTestCase
from django.utils import timezone
from pydantic import ValidationError

from apps.patient_results.api_schemas import RequestOtpRequest, VerifyOtpRequest


class RequestOtpRequestTests(SimpleTestCase):
    def test_parses_trimmed_fields_and_iso_prefix(self) -> None:
        body = RequestOtpRequest.model_validate(
            {
                "phone": " 01763333333 ",
                "date_of_birth": "1990-01-15T12:00:00",
                "captcha_token": " skip ",
                "last_name": " Schmidt ",
            }
        )
        self.assertEqual(body.phone, "01763333333")
        self.assertEqual(body.date_of_birth, date(1990, 1, 15))
        self.assertEqual(body.captcha_token, "skip")
        self.assertEqual(body.last_name, "Schmidt")

    def test_blank_last_name_and_missing_captcha_are_optional(self) -> None:
        body = RequestOtpRequest.model_validate(
            {
                "phone": "01763333333",
                "date_of_birth": "1990-01-15",
                "last_name": "   ",
            }
        )
        self.assertIsNone(body.last_name)
        self.assertEqual(body.captcha_token, "")

    def test_rejects_blank_phone(self) -> None:
        with self.assertRaises(ValidationError):
            RequestOtpRequest.model_validate(
                {
                    "phone": "  ",
                    "date_of_birth": "1990-01-15",
                    "captcha_token": "skip",
                }
            )

    def test_rejects_future_and_too_old_date_of_birth(self) -> None:
        with self.assertRaises(ValidationError):
            RequestOtpRequest.model_validate(
                {
                    "phone": "01763333333",
                    "date_of_birth": "2090-01-15",
                    "captcha_token": "skip",
                }
            )
        too_old = (timezone.now().date() - timedelta(days=120 * 365 + 1)).isoformat()
        with self.assertRaises(ValidationError):
            RequestOtpRequest.model_validate(
                {
                    "phone": "01763333333",
                    "date_of_birth": too_old,
                    "captcha_token": "skip",
                }
            )


class VerifyOtpRequestTests(SimpleTestCase):
    def test_parses_six_digit_otp(self) -> None:
        body = VerifyOtpRequest.model_validate(
            {
                "phone": "01764444444",
                "date_of_birth": "1988-07-20",
                "otp_code": " 654321 ",
            }
        )
        self.assertEqual(body.otp_code, "654321")
        self.assertIsNone(body.last_name)

    def test_rejects_non_six_digit_otp(self) -> None:
        with self.assertRaises(ValidationError):
            VerifyOtpRequest.model_validate(
                {
                    "phone": "01764444444",
                    "date_of_birth": "1988-07-20",
                    "otp_code": "12",
                }
            )
