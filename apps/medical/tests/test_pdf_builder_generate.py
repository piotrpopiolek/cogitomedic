"""Tests for generate_befund_pdf / build_merged_preview_pdf_bytes external-PDF branches."""

from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from pypdf import PdfReader, PdfWriter

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.integrations.hidrive import client as hidrive_client
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.external_pdf_service import ExternalPdfCorruptError
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.medical.pdf_builder import (
    AllExternalPdfDownloadsFailed,
    _build_render_context,
    build_merged_preview_pdf_bytes,
    generate_befund_pdf,
    generate_external_upload_pdf,
)
from apps.operations.models import AuditEvent
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
from apps.users.models import StaffUser, StaffUserGender


def _minimal_pdf_bytes() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


def _minimal_pdf_bytes_with_title() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.add_metadata({"/Title": "Lab fixture title"})
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
    def test_generate_befund_refuses_without_lab_when_all_downloads_fail(
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
            with self.assertRaises(AllExternalPdfDownloadsFailed):
                generate_befund_pdf(self.version)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.MATCHED)

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
    def test_generate_befund_marks_attachment_accepted_when_merge_succeeds(
        self,
        dl_mock: MagicMock,
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
        with self.settings(MEDIA_ROOT=str(self.media_root)):
            generate_befund_pdf(self.version)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.ACCEPTED)

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

    def test_publication_date_display_uses_last_published_when_version_published_at_null(
        self,
    ) -> None:
        lp = timezone.make_aware(datetime(2026, 4, 10, 14, 0, 0))
        MedicalDocument.objects.filter(pk=self.medical_doc.pk).update(
            last_published_at=lp
        )
        MedicalDocumentVersion.objects.filter(pk=self.version.pk).update(
            published_at=None
        )
        self.version.refresh_from_db()
        self.medical_doc.refresh_from_db()
        ctx = _build_render_context(self.version)
        expected = timezone.localtime(lp).strftime("%d.%m.%Y")
        self.assertEqual(ctx["publication_date_display"], expected)

    @patch("django.utils.timezone.now")
    def test_publication_date_display_for_draft_uses_render_day_not_dash(
        self, now_mock: MagicMock
    ) -> None:
        now_mock.return_value = datetime(2026, 4, 13, 10, 0, 0, tzinfo=dt_timezone.utc)
        MedicalDocument.objects.filter(pk=self.medical_doc.pk).update(
            last_published_at=None
        )
        MedicalDocumentVersion.objects.filter(pk=self.version.pk).update(
            published_at=None,
            version_status=DocVersionStatus.DRAFT,
        )
        self.version.refresh_from_db()
        self.medical_doc.refresh_from_db()
        ctx = _build_render_context(self.version)
        self.assertNotEqual(ctx["publication_date_display"], "–")
        expected = timezone.localtime(timezone.now()).strftime("%d.%m.%Y")
        self.assertEqual(ctx["publication_date_display"], expected)

    def test_reporting_physician_display_uses_published_by_when_set(self) -> None:
        self.doctor.first_name = "Anna"
        self.doctor.last_name = "Schmidt"
        self.doctor.save(update_fields=["first_name", "last_name"])
        self.version.published_by_user = self.doctor
        self.version.save(update_fields=["published_by_user"])
        ctx = _build_render_context(self.version)
        self.assertEqual(ctx["reporting_physician_display"], "Schmidt Anna")

    def test_global_assessment_lines_skips_empty_and_dash_placeholder(self) -> None:
        ctx = _build_render_context(self.version)
        lines = ctx["global_assessment_lines"]
        for line in lines:
            self.assertTrue(line.strip())
            self.assertNotEqual(line.strip(), "-")

    def test_global_assessment_lines_empty_when_all_placeholders(self) -> None:
        MedicalDocumentVersion.objects.filter(pk=self.version.pk).update(
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": [],
            },
            diagnosis_code="",
            procedure_code="",
        )
        self.version.refresh_from_db()
        ctx = _build_render_context(self.version)
        self.assertEqual(ctx["global_assessment_lines"], [])

    def test_reporting_physician_display_falls_back_to_document_creator(self) -> None:
        self.doctor.first_name = "Ben"
        self.doctor.last_name = "Weber"
        self.doctor.save(update_fields=["first_name", "last_name"])
        MedicalDocument.objects.filter(pk=self.medical_doc.pk).update(
            updated_by_user_id=None
        )
        MedicalDocumentVersion.objects.filter(pk=self.version.pk).update(
            published_by_user_id=None
        )
        self.medical_doc.refresh_from_db()
        self.version.refresh_from_db()
        ctx = _build_render_context(self.version)
        self.assertEqual(ctx["reporting_physician_display"], "Weber Ben")

    def test_pdf_signoff_footer_uses_female_specialty_when_gender_female(self) -> None:
        self.doctor.first_name = "Anna"
        self.doctor.last_name = "Schmidt"
        self.doctor.gender = StaffUserGender.FEMALE
        self.doctor.professional_title = "Dr. med."
        self.doctor.save(
            update_fields=["first_name", "last_name", "gender", "professional_title"]
        )
        self.version.published_by_user = self.doctor
        self.version.save(update_fields=["published_by_user"])
        ctx = _build_render_context(self.version)
        lines = ctx["pdf_signoff_footer_lines"]
        self.assertIsNotNone(lines)
        self.assertGreaterEqual(len(lines), 4)
        self.assertEqual(lines[1], "Dr. med. Anna Schmidt")
        self.assertIn("Fachärztin", lines[2])
        self.assertIn("Teledermatologische", lines[3])

    def test_pdf_signoff_footer_uses_male_specialty_when_gender_male(self) -> None:
        self.doctor.first_name = "Paul"
        self.doctor.last_name = "Meyer"
        self.doctor.gender = StaffUserGender.MALE
        self.doctor.professional_title = "Dr. med."
        self.doctor.save(
            update_fields=["first_name", "last_name", "gender", "professional_title"]
        )
        self.version.published_by_user = self.doctor
        self.version.save(update_fields=["published_by_user"])
        ctx = _build_render_context(self.version)
        lines = ctx["pdf_signoff_footer_lines"]
        self.assertIsNotNone(lines)
        self.assertEqual(lines[1], "Dr. med. Paul Meyer")
        self.assertEqual(lines[2], "Facharzt für Dermatologie")

    def test_pdf_signoff_unspecified_gender_uses_male_specialty_and_first_last_name(
        self,
    ) -> None:
        """Legacy accounts without gender: male German line (not Facharzt/-in slash form)."""
        self.doctor.first_name = "Piotr"
        self.doctor.last_name = "Popiołek"
        self.doctor.gender = StaffUserGender.UNSPECIFIED
        self.doctor.professional_title = "Dr. med."
        self.doctor.save(
            update_fields=["first_name", "last_name", "gender", "professional_title"]
        )
        self.version.published_by_user = self.doctor
        self.version.save(update_fields=["published_by_user"])
        ctx = _build_render_context(self.version)
        lines = ctx["pdf_signoff_footer_lines"]
        self.assertIsNotNone(lines)
        self.assertEqual(lines[1], "Dr. med. Piotr Popiołek")
        self.assertEqual(lines[2], "Facharzt für Dermatologie")


class GenerateExternalUploadPdfTests(GenerateBefundPdfExternalTests):
    def setUp(self) -> None:
        super().setUp()
        MedicalDocument.objects.filter(pk=self.medical_doc.pk).update(
            source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD
        )
        self.medical_doc.refresh_from_db()

    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_generate_external_upload_raises_domain_error_without_attachment(
        self,
        dl_mock: MagicMock,
    ) -> None:
        with self.settings(MEDIA_ROOT=str(self.media_root)):
            with self.assertRaises(DomainError) as ctx:
                generate_external_upload_pdf(self.version)
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.external_upload_generate_pdf_no_attachment",
        )
        dl_mock.assert_not_called()

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_generate_external_upload_conditional_promote_idempotent_on_retry(
        self,
        dl_mock: MagicMock,
    ) -> None:
        pdf = _minimal_pdf_bytes()
        dl_mock.return_value = pdf
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/ext-up.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/ext-up.pdf",
            original_filename="ext-up.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self.version.external_selected_attachment = att
        self.version.save(update_fields=["external_selected_attachment"])

        with self.settings(MEDIA_ROOT=str(self.media_root)):
            generate_external_upload_pdf(self.version)
            generate_external_upload_pdf(self.version)

        self.assertEqual(dl_mock.call_count, 2)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.ACCEPTED)

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_generate_external_upload_corrupt_demotes_matched_and_raises_domain_error(
        self,
        dl_mock: MagicMock,
    ) -> None:
        pdf = _minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/ext-corrupt.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/ext-corrupt.pdf",
            original_filename="ext-corrupt.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self.version.external_selected_attachment = att
        self.version.save(update_fields=["external_selected_attachment"])
        dl_mock.side_effect = ExternalPdfCorruptError("bad")

        with self.settings(MEDIA_ROOT=str(self.media_root)):
            with self.assertRaises(DomainError) as ctx:
                generate_external_upload_pdf(self.version)

        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.external_upload_generate_pdf_corrupt",
        )
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.MERGE_FAILED)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="EXTERNAL_PDF_CORRUPT",
                medical_document_id=self.medical_doc.id,
            ).exists()
        )

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_generate_external_upload_infra_error_raises_all_downloads_failed_pattern(
        self,
        dl_mock: MagicMock,
    ) -> None:
        pdf = _minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/ext-down.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/ext-down.pdf",
            original_filename="ext-down.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self.version.external_selected_attachment = att
        self.version.save(update_fields=["external_selected_attachment"])
        dl_mock.side_effect = OSError("hidrive unavailable")

        with self.settings(MEDIA_ROOT=str(self.media_root)):
            with self.assertRaises(AllExternalPdfDownloadsFailed) as ctx:
                generate_external_upload_pdf(self.version)

        self.assertEqual(ctx.exception.medical_document_id, self.medical_doc.id)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.MERGE_FAILED)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="EXTERNAL_PDF_DOWNLOAD_FAILED",
                medical_document_id=self.medical_doc.id,
            ).exists()
        )

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch("apps.medical.pdf_builder.download_external_pdf")
    def test_generate_external_upload_pdf_injects_document_id_metadata(
        self,
        dl_mock: MagicMock,
    ) -> None:
        pdf = _minimal_pdf_bytes_with_title()
        dl_mock.return_value = pdf
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/ext-meta.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/ext-meta.pdf",
            original_filename="ext-meta.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self.version.external_selected_attachment = att
        self.version.save(update_fields=["external_selected_attachment"])

        with self.settings(MEDIA_ROOT=str(self.media_root)):
            rel_path, checksum = generate_external_upload_pdf(self.version)

        self.assertTrue(checksum)
        out_path = self.media_root / rel_path
        reader = PdfReader(str(out_path))
        meta = reader.metadata or {}
        self.assertEqual(
            meta.get("/cogitomedicaldocumentid"),
            str(self.medical_doc.id),
        )
        self.assertEqual(meta.get("/Title"), "Lab fixture title")

    def test_external_upload_metadata_helper_contract(self) -> None:
        """Regression: rewriter must change bytes and set /cogitomedicaldocumentid."""
        from apps.medical import pdf_builder as pb

        doc_id = self.medical_doc.id
        raw = _minimal_pdf_bytes_with_title()
        stamped = pb._external_upload_pdf_bytes_with_document_metadata(raw, doc_id)
        self.assertNotEqual(stamped, raw)
        r2 = PdfReader(BytesIO(stamped))
        self.assertEqual(
            (r2.metadata or {}).get("/cogitomedicaldocumentid"),
            str(doc_id),
        )
