"""Tests for apps.medical.incoming_pdf_scan."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.integrations.hidrive import client as hidrive_client
from apps.integrations.hidrive.client import HiDriveTimeoutError
from apps.medical.incoming_pdf_scan import (
    IncomingMatchStatus,
    evaluate_patient_incoming_match,
    list_incoming_lab_pdf_rows,
    suggest_incoming_pdf_filename,
)
from apps.reception.models import Patient


@override_settings(
    HIDRIVE_USE_MOCK="1",
    HIDRIVE_INCOMING_PATH="/incoming",
)
class IncomingPdfScanTests(TestCase):
    def setUp(self) -> None:
        hidrive_client._MockHiDriveAdapter.reset_test_state()

    def test_list_incoming_lab_pdf_rows_hidrive_error(self) -> None:
        adapter = MagicMock()
        adapter.list_dir.side_effect = RuntimeError("down")
        with patch(
            "apps.medical.incoming_pdf_scan.get_hidrive_adapter",
            return_value=adapter,
        ):
            listing = list_incoming_lab_pdf_rows()
        self.assertFalse(listing.hidrive_ok)
        self.assertEqual(listing.pdf_rows, [])

    def test_list_incoming_lab_pdf_rows_timeout_propagates(self) -> None:
        adapter = MagicMock()
        adapter.list_dir.side_effect = HiDriveTimeoutError("timed out")
        with patch(
            "apps.medical.incoming_pdf_scan.get_hidrive_adapter",
            return_value=adapter,
        ):
            with self.assertRaises(HiDriveTimeoutError):
                list_incoming_lab_pdf_rows(hidrive_total_timeout_seconds=8)

    def test_evaluate_match_matched(self) -> None:
        patient = Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100201",
            email="med@example.com",
        )
        pdf_rows = [
            (
                {"path": "/incoming/Med_Test.pdf"},
                "Med_Test.pdf",
            )
        ]
        result = evaluate_patient_incoming_match(patient, pdf_rows)
        self.assertEqual(result.status, IncomingMatchStatus.MATCHED)
        self.assertEqual(len(result.matched_files), 1)

    def test_evaluate_match_no_file(self) -> None:
        patient = Patient.objects.create(
            first_name="Anna",
            last_name="Nowak",
            date_of_birth=date(1991, 2, 2),
            phone="+48500100202",
            email="anna@example.com",
        )
        pdf_rows = [
            (
                {"path": "/incoming/Other_Person.pdf"},
                "Other_Person.pdf",
            )
        ]
        result = evaluate_patient_incoming_match(patient, pdf_rows)
        self.assertEqual(result.status, IncomingMatchStatus.NO_FILE)

    def test_evaluate_match_rejected_only(self) -> None:
        patient = Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100203",
            email="med3@example.com",
        )
        pdf_rows = [
            (
                {"path": "/incoming/rejected_Med_Test.pdf"},
                "rejected_Med_Test.pdf",
            )
        ]
        result = evaluate_patient_incoming_match(patient, pdf_rows)
        self.assertEqual(result.status, IncomingMatchStatus.REJECTED_ONLY)
        self.assertEqual(result.rejected_filenames, ("rejected_Med_Test.pdf",))

    def test_suggest_filename_uses_dob_when_ambiguous(self) -> None:
        Patient.objects.create(
            first_name="Hans",
            last_name="Muller",
            date_of_birth=date(1985, 3, 12),
            phone="+491111111101",
            email="hans1@example.com",
        )
        Patient.objects.create(
            first_name="Hans",
            last_name="Muller",
            date_of_birth=date(1990, 1, 1),
            phone="+491111111102",
            email="hans2@example.com",
        )
        patient = Patient.objects.get(email="hans1@example.com")
        suggested = suggest_incoming_pdf_filename(patient)
        self.assertEqual(suggested, "Muller_Hans_1985_03_12.pdf")

    def test_suggest_filename_without_ambiguity_uses_undated(self) -> None:
        patient = Patient.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            date_of_birth=date(1985, 3, 12),
            phone="+48500999001",
            email="jan.k@example.com",
        )
        self.assertEqual(
            suggest_incoming_pdf_filename(patient),
            "Kowalski_Jan.pdf",
        )
