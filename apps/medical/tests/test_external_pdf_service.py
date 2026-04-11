"""Tests for HiDrive external PDF gate (apps.medical.external_pdf_service)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from django.db.models import Q
from django.test import SimpleTestCase, TestCase, override_settings

from apps.integrations.hidrive import client as hidrive_client
from apps.medical.external_pdf_service import (
    _ambiguous_undated_stem,
    check_external_pdf_gate,
    logical_path_to_processed,
)
from apps.medical.name_normalize import (
    incoming_stem_norm_lookup_bases,
    normalize_name,
    _stem_without_pdf,
)
from apps.reception.models import Patient


class LogicalPathToProcessedTests(SimpleTestCase):
    @override_settings(
        HIDRIVE_INCOMING_PATH="/incoming",
        HIDRIVE_PROCESSED_PATH="/processed",
    )
    def test_root_incoming_prefix_maps_to_processed(self) -> None:
        self.assertEqual(
            logical_path_to_processed("/incoming/X.pdf"),
            "/processed/X.pdf",
        )


@override_settings(HIDRIVE_USE_MOCK="1")
class ExternalPdfGateTests(TestCase):
    def setUp(self) -> None:
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        incoming_stem_norm_lookup_bases.cache_clear()

    def test_gate_passes_when_list_dir_raises(self) -> None:
        """HiDrive outage must not hard-block doctor workflow (no attachment sync)."""
        patient = Patient.objects.create(
            first_name="Down",
            last_name="HiDrive",
            date_of_birth=date(1988, 8, 8),
            phone="+48500100299",
            email="down@example.com",
        )
        adapter = MagicMock()
        adapter.list_dir.side_effect = RuntimeError("connection reset")
        with patch(
            "apps.medical.external_pdf_service.get_hidrive_adapter",
            return_value=adapter,
        ):
            gate = check_external_pdf_gate(
                patient,
                error_no_file="NO_FILE",
                error_no_pdfs_in_folder="NO_PDFS",
                error_ambiguous="AMBIG",
                error_hidrive="HIDRIVE",
            )
        self.assertTrue(gate.passed)
        self.assertEqual(gate.matched_files, ())
        self.assertEqual(gate.error_message, "HIDRIVE")
        self.assertTrue(gate.skip_attachment_sync)

    def test_gate_fails_when_incoming_empty(self) -> None:
        patient = Patient.objects.create(
            first_name="Anna",
            last_name="Schmidt",
            date_of_birth=date(1991, 5, 5),
            phone="+491234567890",
            email="anna@example.com",
        )
        gate = check_external_pdf_gate(
            patient,
            error_no_file="NO_FILE",
            error_no_pdfs_in_folder="NO_PDFS",
            error_ambiguous="AMBIG",
            error_hidrive="HIDRIVE",
        )
        self.assertFalse(gate.passed)
        self.assertEqual(gate.error_message, "NO_PDFS")

    def test_gate_passes_for_matching_file(self) -> None:
        patient = Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100201",
            email="med@example.com",
        )
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Med_Test.pdf",
                    "path": "/incoming/Med_Test.pdf",
                    "size": 10,
                    "mtime": None,
                }
            ],
        )
        gate = check_external_pdf_gate(
            patient,
            error_no_file="NO_FILE",
            error_no_pdfs_in_folder="NO_PDFS",
            error_ambiguous="AMBIG",
            error_hidrive="HIDRIVE",
        )
        self.assertTrue(gate.passed)
        self.assertEqual(len(gate.matched_files), 1)
        self.assertEqual(gate.matched_files[0].name, "Med_Test.pdf")

    def test_gate_uses_path_when_name_omits_pdf_extension(self) -> None:
        """HiDrive API may return basename without ``.pdf`` in ``name`` while ``path`` is complete."""
        patient = Patient.objects.create(
            first_name="Jean Christophe",
            last_name="Scheider",
            date_of_birth=date(1985, 3, 15),
            phone="+491111111111",
            email="jc.scheider@example.com",
        )
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Jean_Christophe_Scheider",
                    "path": "/incoming/Jean_Christophe_Scheider.pdf",
                    "size": 10,
                    "mtime": None,
                }
            ],
        )
        hidrive_client._MockHiDriveAdapter.seed_file(
            "/incoming/Jean_Christophe_Scheider.pdf", b"%PDF-1.4"
        )
        gate = check_external_pdf_gate(
            patient,
            error_no_file="NO_FILE",
            error_no_pdfs_in_folder="NO_PDFS",
            error_ambiguous="AMBIG",
            error_hidrive="HIDRIVE",
        )
        self.assertTrue(gate.passed)
        self.assertEqual(gate.matched_files[0].name, "Jean_Christophe_Scheider.pdf")

    def test_gate_skips_rejected_prefix(self) -> None:
        patient = Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100202",
            email="med2@example.com",
        )
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "rejected_Med_Test.pdf",
                    "path": "/incoming/rejected_Med_Test.pdf",
                    "size": 10,
                    "mtime": None,
                }
            ],
        )
        gate = check_external_pdf_gate(
            patient,
            error_no_file="NO_FILE",
            error_no_pdfs_in_folder="NO_PDFS",
            error_ambiguous="AMBIG",
            error_hidrive="HIDRIVE",
        )
        self.assertFalse(gate.passed)
        self.assertEqual(gate.error_message, "NO_FILE")

    def test_ambiguous_stem_prefilter_narrows_to_colliding_patients(self) -> None:
        """Regression: DB prefilter must ignore unrelated patients (indexed keys)."""
        for i in range(35):
            Patient.objects.create(
                first_name=f"Zed{i}",
                last_name=f"Unique{i}",
                date_of_birth=date(2000, 1, 1),
                phone=f"485001003{i:02d}",
                email=f"zed{i}@example.com",
            )
        Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="48500100399",
            email="ambig_a@example.com",
        )
        Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1992, 2, 2),
            phone="48500100398",
            email="ambig_b@example.com",
        )
        norm = normalize_name(_stem_without_pdf("Med_Test"))
        bases = incoming_stem_norm_lookup_bases(norm)
        narrowed = Patient.objects.filter(
            Q(incoming_pdf_name_key_fl__in=bases)
            | Q(incoming_pdf_name_key_lf__in=bases)
        ).count()
        self.assertEqual(narrowed, 2)
        self.assertTrue(_ambiguous_undated_stem("Med_Test"))

    def test_gate_ambiguous_without_dob_in_filename(self) -> None:
        Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100203",
            email="a@example.com",
        )
        Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1992, 2, 2),
            phone="+48500100204",
            email="b@example.com",
        )
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Med_Test.pdf",
                    "path": "/incoming/Med_Test.pdf",
                    "size": 10,
                    "mtime": None,
                }
            ],
        )
        patient = Patient.objects.get(email="a@example.com")
        gate = check_external_pdf_gate(
            patient,
            error_no_file="NO_FILE",
            error_no_pdfs_in_folder="NO_PDFS",
            error_ambiguous="AMBIG",
            error_hidrive="HIDRIVE",
        )
        self.assertFalse(gate.passed)
        self.assertEqual(gate.error_message, "AMBIG")

    def test_gate_no_match_when_incoming_has_unrelated_pdf(self) -> None:
        patient = Patient.objects.create(
            first_name="Anna",
            last_name="Schmidt",
            date_of_birth=date(1991, 5, 5),
            phone="+491234567891",
            email="anna2@example.com",
        )
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Other_Kowalski.pdf",
                    "path": "/incoming/Other_Kowalski.pdf",
                    "size": 10,
                    "mtime": None,
                }
            ],
        )
        gate = check_external_pdf_gate(
            patient,
            error_no_file="NO_FILE",
            error_no_pdfs_in_folder="NO_PDFS",
            error_ambiguous="AMBIG",
            error_hidrive="HIDRIVE",
        )
        self.assertFalse(gate.passed)
        self.assertEqual(gate.error_message, "NO_FILE")
