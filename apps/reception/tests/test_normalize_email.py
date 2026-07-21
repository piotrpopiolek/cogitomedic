"""Tests for normalize_email_for_storage and Patient.save email cleanup."""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase, TestCase

from apps.reception.models import Patient
from apps.reception.patient_identity import normalize_email_for_storage


class NormalizeEmailForStorageTests(SimpleTestCase):
    def test_strips_leading_and_trailing_spaces(self) -> None:
        self.assertEqual(
            normalize_email_for_storage("  aaron96@web.de  "),
            "aaron96@web.de",
        )

    def test_removes_nbsp_and_internal_whitespace(self) -> None:
        self.assertEqual(
            normalize_email_for_storage("\u00a0laci cilano@gmail.com"),
            "lacicilano@gmail.com",
        )

    def test_lowercases(self) -> None:
        self.assertEqual(
            normalize_email_for_storage("Aaron96@Web.DE"),
            "aaron96@web.de",
        )

    def test_empty_and_none(self) -> None:
        self.assertEqual(normalize_email_for_storage(""), "")
        self.assertEqual(normalize_email_for_storage(None), "")


class PatientEmailSaveNormalizationTests(TestCase):
    def test_save_strips_spaces_from_email(self) -> None:
        patient = Patient(
            first_name="Test",
            last_name="Email",
            date_of_birth=date(1990, 1, 1),
            phone="1761234567",
            email="  Foo@Example.COM ",
        )
        patient.save()
        patient.refresh_from_db()
        self.assertEqual(patient.email, "foo@example.com")
