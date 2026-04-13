"""Tests for generate_befund_pdf / build_merged_preview_pdf_bytes external-PDF branches."""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter

from apps.core.api_utils import assign_group_to_test_user
from apps.integrations.hidrive import client as hidrive_client
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.external_pdf_service import ExternalPdfCorruptError
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.medical.pdf_builder import (
    build_merged_preview_pdf_bytes,
    generate_befund_pdf,
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


def _minimal_pdf_bytes() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


_MINIMAL_MEDICAL_PAYLOAD = {
    "schema_version": 1,
    "authoring_locale": "de-DE",
    "lesions": [],
    "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
    "fitzpatrick_type": "TYPE_III",
    "overall_image_assessment": "NO_CONTROL_NEEDED",
    "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
    "final_assessment": "NO_HIGH_GRADE_SUSPICION",
}


class GenerateBefundPdfExternalTests(TestCase):
    def setUp(self) -> None:
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        self._media = tempfile.TemporaryDirectory()
        self.addCleanup(self._media.cleanup)
        self.media_root = Path(self._media.name)

        self.doctor = StaffUser.objects.create_user(
            username="pdf-gen-doc",
            email="pdfg@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        rec = StaffUser.objects.create_user(
            username="pdf-gen-rec",
            email="pdfgr@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")
        clinic = ClinicSite.objects.create(code="PDFG", name="Pdf Gen")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="P1", name="P1")
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
            phone="+48500100999",
            email="pdfgenpatient@example.com",
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
            signature_sha256="c" * 64,
        )
        self.medical_doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        self.version = MedicalDocumentVersion.objects.create(
            medical_document=self.medical_doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            pdf_generation_status=PdfStatus.PENDING,
            medical_payload_schema_version=1,
            medical_payload=_MINIMAL_MEDICAL_PAYLOAD,
        )

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_generate_befund_marks_attachment_merge_failed_on_corrupt_download(
        self,
        dl_mock: MagicMock,
    ) -> None:
        dl_mock.side_effect = ExternalPdfCorruptError("bad")
        pdf = _minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Med_Test.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.settings(MEDIA_ROOT=str(self.media_root)):
            generate_befund_pdf(self.version)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.MERGE_FAILED)

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_generate_befund_marks_attachment_merge_failed_on_generic_download_error(
        self,
        dl_mock: MagicMock,
    ) -> None:
        dl_mock.side_effect = OSError("hidrive down")
        pdf = _minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Med_Test.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.settings(MEDIA_ROOT=str(self.media_root)):
            generate_befund_pdf(self.version)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.MERGE_FAILED)

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.safe_merge_pdfs")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_generate_befund_bulk_marks_merge_failed_when_safe_merge_returns_false(
        self,
        dl_mock: MagicMock,
        merge_mock: MagicMock,
    ) -> None:
        ext = _minimal_pdf_bytes()
        dl_mock.return_value = ext
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Med_Test.pdf", ext)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        merge_mock.return_value = (_minimal_pdf_bytes(), False)
        with self.settings(MEDIA_ROOT=str(self.media_root)):
            generate_befund_pdf(self.version)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.MERGE_FAILED)

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_build_merged_preview_warns_on_corrupt_external(
        self,
        dl_mock: MagicMock,
    ) -> None:
        dl_mock.side_effect = ExternalPdfCorruptError("bad")
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        _pdf, warn = build_merged_preview_pdf_bytes(self.version)
        self.assertIsNotNone(_pdf)
        self.assertIn("external_pdf_corrupt", (warn or "").lower())

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_build_merged_preview_warns_on_download_failure(
        self,
        dl_mock: MagicMock,
    ) -> None:
        dl_mock.side_effect = RuntimeError("simulated HiDrive failure")
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Med_Test.pdf",
            original_filename="Med_Test.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        _pdf, warn = build_merged_preview_pdf_bytes(self.version)
        self.assertIsNotNone(_pdf)
        self.assertIn("external_pdf_download_failed", (warn or "").lower())
