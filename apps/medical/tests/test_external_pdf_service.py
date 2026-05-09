"""Tests for HiDrive external PDF gate (apps.medical.external_pdf_service)."""

from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.db.models import Q
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter

from apps.core.api_utils import assign_group_to_test_user
from apps.integrations.hidrive import client as hidrive_client
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.external_pdf_service import (
    ExternalPdfCorruptError,
    MatchedIncomingFile,
    _ambiguous_undated_stem,
    check_external_pdf_gate,
    create_attachment_records,
    download_external_pdf,
    hidrive_incoming_dir,
    hidrive_processed_dir,
    logical_path_to_processed,
    reject_external_pdf,
)
from apps.medical.models import (
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
)
from apps.medical.name_normalize import (
    incoming_stem_norm_lookup_bases,
    normalize_name,
    _stem_without_pdf,
)
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientFormSession,
    QueueEntry,
    QueueEntryStatus,
    QueueStatus,
)
from apps.users.models import StaffUser


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

    @override_settings(
        HIDRIVE_INCOMING_PATH="incoming",
        HIDRIVE_PROCESSED_PATH="processed",
    )
    def test_dirs_normalize_missing_leading_slash_from_settings(self) -> None:
        self.assertEqual(hidrive_incoming_dir(), "/incoming")
        self.assertEqual(hidrive_processed_dir(), "/processed")

    @override_settings(
        HIDRIVE_INCOMING_PATH="/incoming",
        HIDRIVE_PROCESSED_PATH="/processed",
    )
    def test_logical_path_outside_incoming_uses_basename_under_processed(self) -> None:
        self.assertEqual(
            logical_path_to_processed("/other/X.pdf"),
            "/processed/X.pdf",
        )


@override_settings(
    HIDRIVE_USE_MOCK="1",
    HIDRIVE_INCOMING_PATH="/incoming",
    HIDRIVE_PROCESSED_PATH="/processed",
    HIDRIVE_PATIENTS_DIR_PREFIX="/patients",
)
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

    def test_gate_skips_reception_external_upload_subtree(self) -> None:
        """PDFs under ``/incoming/external-upload/`` are reception app uploads — not lab gate."""
        patient = Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100255",
            email="gate.external.upload@example.com",
        )
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Med_Test.pdf",
                    "path": "/incoming/Med_Test.pdf",
                    "size": 10,
                    "mtime": None,
                },
                {
                    "name": "Med_Test.pdf",
                    "path": "/incoming/external-upload/00000000-0000-4000-8000-000000000001/Med_Test.pdf",
                    "size": 10,
                    "mtime": None,
                },
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
        self.assertEqual(gate.matched_files[0].path, "/incoming/Med_Test.pdf")

    def test_gate_ignores_only_external_upload_pdfs_for_lab_gate(self) -> None:
        patient = Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100256",
            email="gate.only.external@example.com",
        )
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Med_Test.pdf",
                    "path": "/incoming/external-upload/00000000-0000-4000-8000-000000000002/Med_Test.pdf",
                    "size": 10,
                    "mtime": None,
                },
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
        self.assertEqual(gate.error_message, "NO_PDFS")

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

    def test_gate_dated_filename_matches_only_correct_homonym(self) -> None:
        """§12: two same name+different DOB; dated stem resolves to one patient."""
        Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="48500101001",
            email="hom_a@example.com",
        )
        Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1992, 2, 2),
            phone="48500101002",
            email="hom_b@example.com",
        )
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Med_Test_1990_01_01.pdf",
                    "path": "/incoming/Med_Test_1990_01_01.pdf",
                    "size": 10,
                    "mtime": None,
                }
            ],
        )
        patient_a = Patient.objects.get(email="hom_a@example.com")
        gate_a = check_external_pdf_gate(
            patient_a,
            error_no_file="NO_FILE",
            error_no_pdfs_in_folder="NO_PDFS",
            error_ambiguous="AMBIG",
            error_hidrive="HIDRIVE",
        )
        self.assertTrue(gate_a.passed)
        self.assertEqual(len(gate_a.matched_files), 1)
        self.assertEqual(gate_a.matched_files[0].name, "Med_Test_1990_01_01.pdf")

        patient_b = Patient.objects.get(email="hom_b@example.com")
        gate_b = check_external_pdf_gate(
            patient_b,
            error_no_file="NO_FILE",
            error_no_pdfs_in_folder="NO_PDFS",
            error_ambiguous="AMBIG",
            error_hidrive="HIDRIVE",
        )
        self.assertFalse(gate_b.passed)
        self.assertEqual(gate_b.error_message, "NO_FILE")

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


def _minimal_pdf_bytes() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


@override_settings(
    HIDRIVE_USE_MOCK="1",
    HIDRIVE_INCOMING_PATH="/incoming",
    HIDRIVE_PROCESSED_PATH="/processed",
    HIDRIVE_PATIENTS_DIR_PREFIX="/patients",
)
class ExternalPdfServiceDbTests(TestCase):
    """create_attachment_records, download, reject, and model __str__."""

    def setUp(self) -> None:
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        self.doctor = StaffUser.objects.create_user(
            username="ext-pdf-doc",
            email="ext@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        rec = StaffUser.objects.create_user(
            username="ext-pdf-rec",
            email="rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")
        clinic = ClinicSite.objects.create(code="EXT", name="Ext Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="E1", name="E1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=rec,
        )
        patient = Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100901",
            email="extpatient@example.com",
        )
        qe = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=rec,
        )
        sess = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=rec,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=sess,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        self.medical_doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )

    def test_external_pdf_attachment_str_includes_status(self) -> None:
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self.assertIn("Med_Test.pdf", str(att))
        self.assertIn("MATCHED", str(att))

    def test_create_attachment_records_prunes_stale_paths(self) -> None:
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/old.pdf",
            original_filename="old.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        matched = (MatchedIncomingFile(name="new.pdf", path="/incoming/new.pdf"),)
        out = create_attachment_records(self.medical_doc, matched)
        self.assertEqual(len(out), 1)
        self.assertFalse(
            ExternalPdfAttachment.objects.filter(
                hidrive_remote_path="/incoming/old.pdf"
            ).exists()
        )

    def test_download_external_pdf_happy_path(self) -> None:
        pdf = _minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Med_Test.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        data = download_external_pdf(att)
        self.assertEqual(data, pdf)

    def test_download_external_pdf_corrupt_raises(self) -> None:
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Med_Test.pdf", b"xxx")
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.assertRaises(ExternalPdfCorruptError):
            download_external_pdf(att)

    @patch("apps.medical.external_pdf_service.PdfReader")
    def test_download_external_pdf_raises_when_no_pages(
        self, reader_cls: MagicMock
    ) -> None:
        inst = MagicMock()
        inst.pages = []
        reader_cls.return_value = inst
        hidrive_client._MockHiDriveAdapter.seed_file(
            "/incoming/Med_Test.pdf", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.assertRaises(ExternalPdfCorruptError):
            download_external_pdf(att)

    def test_reject_external_pdf_noop_when_already_rejected(self) -> None:
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/rejected_x.pdf",
            original_filename="rejected_x.pdf",
            status=ExternalPdfStatus.REJECTED,
        )
        reject_external_pdf(att)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.REJECTED)

    def test_reject_external_pdf_noop_when_filename_already_rejected_prefix(
        self,
    ) -> None:
        pdf = _minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file(
            "/incoming/rejected_Med_Test.pdf", pdf
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/rejected_Med_Test.pdf",
            original_filename="rejected_Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        reject_external_pdf(att)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.REJECTED)
