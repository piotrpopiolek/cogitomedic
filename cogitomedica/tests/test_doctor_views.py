"""Smoke tests for cogitomedica/doctor_views.py."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone
from pypdf import PdfWriter

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.operations.models import AuditEvent
from apps.outbox.models import OutboxEvent, OutboxStatus
from apps.medical.external_pdf_service import GateResult, MatchedIncomingFile
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
    PaperIntakeAuthorization,
    PdfStatus,
)
from apps.reception.patient_identity import (
    normalize_patient_name_for_storage as _stored_patient_name,
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


def _doctor_panel_data_from_detail_html(html: str) -> dict:
    """Parse ``panel_data`` embedded via ``json_script`` on doctor detail."""
    match = re.search(
        r'<script[^>]+id="doctor-panel-data"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None, "doctor-panel-data script not found"
    return json.loads(match.group(1))


def _minimal_pdf_bytes() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


class DoctorViewsSmokeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "test-pass"
        self.doctor = StaffUser.objects.create_user(
            username="doc",
            email="doc@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        self.reception_user = StaffUser.objects.create_user(
            username="rec",
            email="rec@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")

        self.manager_user = StaffUser.objects.create_user(
            username="mgr",
            email="mgr@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(self.manager_user, "Manager")

    # -- helpers ------------------------------------------------

    def _login_doctor(self):
        self.client.force_login(self.doctor)

    def _assert_paper_intake_modal_markup(self, html: str) -> None:
        """Regression: in-page modal for paper create; no native window.confirm."""
        self.assertIn('id="paper-intake-confirm-modal"', html)
        self.assertIn("js-paper-intake-create-form", html)
        self.assertNotIn(
            "window.confirm",
            html,
            msg="Paper intake create must not use browser native confirm().",
        )

    # ==========================================================
    # Login
    # ==========================================================

    def test_login_get_returns_200(self):
        resp = self.client.get("/doctor/login/")
        self.assertEqual(resp.status_code, 200)

    def test_login_post_valid_doctor_redirects(self):
        resp = self.client.post(
            "/doctor/login/",
            {"username": "doc", "password": self.password},
        )
        self.assertEqual(resp.status_code, 302)

    def test_login_post_valid_manager_redirects(self):
        resp = self.client.post(
            "/doctor/login/",
            {"username": "mgr", "password": self.password},
        )
        self.assertEqual(resp.status_code, 302)

    # ==========================================================
    # Guard: anonymous and wrong role
    # ==========================================================

    def test_list_anonymous_redirects_to_login(self):
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_list_reception_user_redirects(self):
        self.client.force_login(self.reception_user)
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    # ==========================================================
    # List
    # ==========================================================

    def test_list_doctor_returns_200(self):
        self._login_doctor()
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 200)

    def test_list_includes_dark_mode_classes(self) -> None:
        self._login_doctor()
        html = self.client.get("/doctor/").content.decode()
        self.assertIn("cogitomedica/css/cogitomedica-brand.css", html)
        self.assertIn("cogitomedica/css/admin-list-pagination.css", html)
        self.assertIn("dark:bg-base-900", html)
        self.assertIn("dark:text-base-300", html)
        self.assertIn("dark:border-base-700", html)

    def test_list_includes_row_color_legend(self) -> None:
        self._login_doctor()
        html = self.client.get("/doctor/").content.decode()
        self.assertIn('role="note"', html)

    def test_list_hides_oversight_filters_for_doctor(self) -> None:
        self._login_doctor()
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn('name="published_by_user_id"', html)
        self.assertNotIn('name="scope"', html)

    def test_list_includes_published_by_doctor_select_for_manager(self) -> None:
        self.client.force_login(self.manager_user)
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="published_by_user_id"', html)
        self.assertIn('id="id_published_by_user_id"', html)

    def test_list_manager_returns_200(self):
        self.client.force_login(self.manager_user)
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 200)

    def test_list_lang_param_strips_and_redirects(self):
        self._login_doctor()
        resp = self.client.get("/doctor/?lang=pl")
        self.assertEqual(resp.status_code, 302)

    # ==========================================================
    # Logout
    # ==========================================================

    def test_logout_post_redirects_to_login(self):
        self._login_doctor()
        resp = self.client.post("/doctor/logout/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    # ==========================================================
    # Document detail – nonexistent UUID
    # ==========================================================

    def test_detail_nonexistent_returns_404(self):
        self._login_doctor()
        url = f"/doctor/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    # ==========================================================
    # Open by queue – nonexistent UUID
    # ==========================================================

    def test_open_by_queue_nonexistent_returns_error(self):
        self._login_doctor()
        url = f"/doctor/open/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_open_by_queue_cancelled_entry_returns_404_without_creating_document(
        self,
    ) -> None:
        """Direct /doctor/open/{uuid}/ must not create Befund on cancelled visit."""
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="CN", name="Cancelled Open Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="C1", name="C1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Ann",
            last_name="Cancelled",
            date_of_birth=date(1988, 3, 3),
            phone="+48500997766",
            email="cancelled.open@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.CANCELLED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="d" * 64,
        )

        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(
            MedicalDocument.objects.filter(queue_entry_id=entry.id).exists()
        )

    def test_open_by_queue_returns_400_when_intake_reopened(self):
        """Befund must not be created while intake is REOPENED (patient editing again)."""
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="RO", name="Reopen Open Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ReopenBlock",
            date_of_birth=date(1990, 1, 1),
            phone="+48500999111",
            email="reopenblock@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.REOPENED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"reopened", resp.content.lower())

    def test_open_by_queue_external_upload_redirects_skips_create_or_get(
        self,
    ) -> None:
        """Reception external-upload doc on REOPENED intake: doctor opens detail, no Befund create."""
        from apps.medical.services import create_external_upload_medical_document

        self._login_doctor()
        clinic = ClinicSite.objects.create(code="EU", name="Ext Upload Open Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="E1", name="E1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ExtUploadOpen",
            date_of_birth=date(1991, 6, 6),
            phone="+48500111222",
            email="extuploadopen@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.REOPENED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        ext_doc = create_external_upload_medical_document(
            queue_entry_id=entry.id,
            created_by_user_id=self.reception_user.id,
        )
        self.assertEqual(ext_doc.source_type, MedicalDocumentSourceType.EXTERNAL_UPLOAD)

        with patch("cogitomedica.doctor_views.create_or_get_medical_document") as m_cog:
            resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
            m_cog.assert_not_called()

        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"/doctor/{ext_doc.id}/", resp.url)
        self.assertIn("lang=en", resp.url)

    @patch("cogitomedica.doctor_views.acquire_document_lock")
    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_external_upload_document_detail_skips_gate_and_lock(
        self,
        gate_mock: MagicMock,
        lock_mock: MagicMock,
    ) -> None:
        from apps.medical.services import create_external_upload_medical_document

        gate_mock.side_effect = AssertionError(
            "check_external_pdf_gate must not run for EXTERNAL_UPLOAD draft detail"
        )
        lock_mock.side_effect = AssertionError(
            "acquire_document_lock must not run for EXTERNAL_UPLOAD draft detail"
        )

        self._login_doctor()
        clinic = ClinicSite.objects.create(code="ED", name="Ext Detail Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="D1", name="D1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ExtDetail",
            date_of_birth=date(1993, 3, 3),
            phone="+48500111333",
            email="extdetail@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        ext_doc = create_external_upload_medical_document(
            queue_entry_id=entry.id,
            created_by_user_id=self.reception_user.id,
        )
        self.assertEqual(ext_doc.source_type, MedicalDocumentSourceType.EXTERNAL_UPLOAD)

        resp = self.client.get(f"/doctor/{ext_doc.id}/?lang=de")
        self.assertEqual(resp.status_code, 200)
        gate_mock.assert_not_called()
        lock_mock.assert_not_called()
        html = resp.content.decode("utf-8")
        m = re.search(
            r'<script id="doctor-panel-data" type="application/json">(.+?)</script>',
            html,
            re.S,
        )
        self.assertIsNotNone(m)
        assert m is not None  # narrow for mypy
        panel = json.loads(m.group(1))
        self.assertTrue(panel.get("externalUploadReadOnly"))
        self.assertNotIn('id="befund-form"', resp.content.decode("utf-8"))

    @patch("cogitomedica.doctor_views.acquire_document_lock")
    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_external_upload_readonly_draft_detail_hides_preview_until_published(
        self,
        _gate: MagicMock,
        _lock: MagicMock,
    ) -> None:
        """DRAFT external upload: no doctor PDF preview (reception-only until publish)."""
        from apps.medical.services import create_external_upload_medical_document

        self._login_doctor()
        clinic = ClinicSite.objects.create(code="EDL", name="Ext Draft Link Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="D1", name="D1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ExtDraftLink",
            date_of_birth=date(1993, 3, 3),
            phone="+48500111334",
            email="extdraftlink@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        ext_doc = create_external_upload_medical_document(
            queue_entry_id=entry.id,
            created_by_user_id=self.reception_user.id,
        )
        ver = MedicalDocumentVersion.objects.get(
            medical_document_id=ext_doc.id, version_no=1
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=ext_doc,
            hidrive_remote_path="/incoming/draft-href.pdf",
            original_filename="draft-href.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        ver.external_selected_attachment = att
        ver.save(update_fields=["external_selected_attachment_id"])

        ext_doc.refresh_from_db()
        self.assertEqual(ext_doc.status, MedicalDocStatus.DRAFT)

        resp = self.client.get(f"/doctor/{ext_doc.id}/?lang=de")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        panel = _doctor_panel_data_from_detail_html(html)

        self.assertTrue(panel.get("externalUploadReadOnly"))
        self.assertFalse(panel.get("externalUploadLoadAttachmentPanel"))
        self.assertNotIn('id="btn-preview-pdf"', html)
        self.assertNotIn("external-upload/preview-pdf", html)
        self.assertNotIn('id="btn-preview-published-external"', html)

    @patch("apps.medical.services.get_hidrive_adapter")
    @patch("cogitomedica.doctor_views.acquire_document_lock")
    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_external_upload_readonly_published_detail_links_standard_preview(
        self,
        adapter_factory: MagicMock,
        _lock: MagicMock,
        _gate: MagicMock,
    ) -> None:
        """Published EXTERNAL_UPLOAD: PDF link targets ``…/preview-pdf`` (doctor-accessible)."""
        adapter_factory.return_value.upload.return_value = None
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="EPL", name="Ext Pub Link Clinic")
        self.reception_user.clinic_sites.add(clinic)
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="P1", name="P1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ExtPubLink",
            date_of_birth=date(1994, 4, 4),
            phone="+48500111335",
            email="extpublink@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(entry.id),
                "file": SimpleUploadedFile(
                    "lab.pdf", _minimal_pdf_bytes(), content_type="application/pdf"
                ),
            },
        )
        self.assertEqual(up.status_code, 201, up.content)
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        sel = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        self.assertEqual(sel.status_code, 200, sel.content)
        pub = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                    "resend_sms": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(pub.status_code, 200, pub.content)

        self.client.force_login(self.manager_user)
        resp = self.client.get(f"/doctor/{doc_id}/?lang=de")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        panel = _doctor_panel_data_from_detail_html(html)
        self.assertTrue(panel.get("externalUploadReadOnly"))
        self.assertTrue(panel.get("externalUploadLoadAttachmentPanel"))
        self.assertIn(f"/api/v1/medical-documents/{doc_id}/preview-pdf", html)
        self.assertNotIn("external-upload/preview-pdf", html)
        self.assertIn('id="btn-preview-pdf"', html)

    @patch("apps.medical.services.get_hidrive_adapter")
    @patch("cogitomedica.doctor_views.acquire_document_lock")
    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_external_upload_pending_revision_without_attachment_links_published_preview(
        self,
        adapter_factory: MagicMock,
        _gate: MagicMock,
        _lock: MagicMock,
    ) -> None:
        """Pending revision draft without selection falls back to published preview URL."""
        adapter_factory.return_value.upload.return_value = None
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="EPR", name="Ext Pending Rev Clinic")
        self.reception_user.clinic_sites.add(clinic)
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="P2", name="P2")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ExtPendingRev",
            date_of_birth=date(1995, 5, 5),
            phone="+48500111336",
            email="extpendingrev@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="f" * 64,
        )
        self.client.force_login(self.reception_user)
        up = self.client.post(
            "/api/v1/medical-documents/external-upload/upload",
            data={
                "queue_entry_id": str(entry.id),
                "file": SimpleUploadedFile(
                    "lab.pdf", _minimal_pdf_bytes(), content_type="application/pdf"
                ),
            },
        )
        doc_id = up.json()["document_id"]
        att_id = up.json()["attachment_id"]
        self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/select-attachment",
            data=json.dumps({"attachment_id": att_id}),
            content_type="application/json",
        )
        pub = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "publish_locale": "de-DE",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(pub.status_code, 200, pub.content)
        OutboxEvent.objects.filter(
            medical_document_version_id=pub.json()["medical_document_version_id"]
        ).update(status=OutboxStatus.PROCESSED)
        rev = self.client.post(
            f"/api/v1/medical-documents/{doc_id}/external-upload/revision/start",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(rev.status_code, 201, rev.content)
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{doc_id}/?lang=de")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn(f"/api/v1/medical-documents/{doc_id}/preview-pdf", html)
        self.assertNotIn("external-upload/preview-pdf", html)

    def test_open_by_queue_returns_400_when_intake_in_progress(self) -> None:
        """Befund creation requires SUBMITTED intake, not IN_PROGRESS."""
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="IP", name="In Progress Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="InProgress",
            date_of_birth=date(1992, 2, 2),
            phone="+48500888777",
            email="inprogress@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
        )
        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"completed", resp.content.lower())

    def test_open_by_queue_without_intake_returns_400_no_auto_document(self) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="NO", name="No Intake Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="PaperFlow",
            date_of_birth=date(1995, 3, 3),
            phone="+48500777666",
            email="paperflow@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )

        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(MedicalDocument.objects.filter(queue_entry=entry).exists())
        self.assertIn(b"questionnaire", resp.content.lower())

    def test_open_by_queue_without_intake_early_appointment_still_returns_400(
        self,
    ) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="N3", name="No Intake Guard Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="TooEarly",
            date_of_birth=date(1996, 4, 4),
            phone="+48500666555",
            email="tooearly@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=1),
            created_by_user=self.reception_user,
        )

        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(MedicalDocument.objects.filter(queue_entry=entry).exists())

    def test_open_by_queue_without_intake_with_paper_authorization_returns_action_page(
        self,
    ) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PA", name="Paper Auth Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="AuthorizedPaper",
            date_of_birth=date(1993, 3, 3),
            phone="+48500555444",
            email="authorizedpaper@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake",
        )

        list_resp = self.client.get("/doctor/?lang=en")
        self.assertEqual(list_resp.status_code, 302)
        list_resp = self.client.get("/doctor/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertIn(
            f"/doctor/open/{entry.id}/create-no-intake/", list_resp.content.decode()
        )

        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 200)
        lowered = resp.content.lower()
        self.assertTrue(
            b"paper" in lowered or b"papier" in lowered,
            msg="Expected paper-intake wording (EN or DE) in the no-intake action page.",
        )
        self.assertIn(b"create-no-intake", lowered)

    def test_paper_intake_create_confirm_modal_on_list_and_no_intake_page(self) -> None:
        """List + no-intake action page embed shared modal; forms use JS hook, not window.confirm."""
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PM", name="Paper Modal Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="ModalPaper",
            date_of_birth=date(1992, 2, 2),
            phone="+48500333222",
            email="modalpaper@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake for modal regression test",
        )

        list_resp = self.client.get("/doctor/")
        self.assertEqual(list_resp.status_code, 200)
        self._assert_paper_intake_modal_markup(list_resp.content.decode())

        action_resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(action_resp.status_code, 200)
        self._assert_paper_intake_modal_markup(action_resp.content.decode())

    def test_post_create_no_intake_creates_document_and_redirects_to_detail(
        self,
    ) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PC", name="Paper Create Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="CreatePaper",
            date_of_birth=date(1991, 8, 8),
            phone="+48500444333",
            email="createpaper@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake",
        )

        resp = self.client.post(f"/doctor/open/{entry.id}/create-no-intake/?lang=en")

        self.assertEqual(resp.status_code, 302)
        doc = MedicalDocument.objects.get(queue_entry=entry)
        self.assertEqual(doc.source_type, MedicalDocumentSourceType.PAPER_INTAKE)
        self.assertIsNone(doc.intake_form_id)
        self.assertIn(f"/doctor/{doc.id}/?lang=en", resp.url)

    def test_paper_intake_document_detail_panel_has_paper_context_and_ui_keys(
        self,
    ) -> None:
        """Befund detail for PAPER_INTAKE: panel JSON exposes auth snapshot + new UI keys."""
        gate_patcher = patch(
            "cogitomedica.doctor_views.check_external_pdf_gate",
            return_value=GateResult(
                True,
                (),
                None,
                skip_attachment_sync=False,
            ),
        )
        gate_patcher.start()
        self.addCleanup(gate_patcher.stop)

        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PD", name="Paper Detail Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="DetailPaper",
            date_of_birth=date(1990, 1, 2),
            phone="+48500111222",
            email="detailpaper@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake",
        )
        post_resp = self.client.post(
            f"/doctor/open/{entry.id}/create-no-intake/?lang=en",
        )
        self.assertEqual(post_resp.status_code, 302)
        doc = MedicalDocument.objects.get(queue_entry=entry)

        detail_resp = self.client.get(f"/doctor/{doc.id}/?lang=en")
        self.assertEqual(detail_resp.status_code, 200)
        html = detail_resp.content.decode()
        self.assertIn('id="paper-intake-meta"', html)
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert m is not None, "expected doctor-panel-data script in HTML"
        panel = json.loads(m.group(1))
        self.assertEqual(panel["context"]["source_type"], "PAPER_INTAKE")
        auth = panel["context"]["paper_intake_authorization"]
        self.assertIsNotNone(auth)
        self.assertEqual(auth.get("reason"), "Patient delivered paper intake")
        self.assertEqual(
            auth.get("authorized_by_username"),
            self.manager_user.username,
        )
        ui = panel["ui"]
        self.assertIn("detail_paper_intake_notice", ui)
        self.assertIn("detail_paper_auth_heading", ui)
        self.assertTrue(len(ui.get("detail_paper_intake_notice", "")) > 5)

    def test_paper_intake_document_detail_returns_422_when_audit_snapshot_missing(
        self,
    ) -> None:
        gate_patcher = patch(
            "cogitomedica.doctor_views.check_external_pdf_gate",
            return_value=GateResult(
                True,
                (),
                None,
                skip_attachment_sync=False,
            ),
        )
        gate_patcher.start()
        self.addCleanup(gate_patcher.stop)

        self._login_doctor()
        clinic = ClinicSite.objects.create(code="PX", name="Paper Missing Audit Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="NoAuditSnap",
            date_of_birth=date(1988, 8, 8),
            phone="+48500222333",
            email="noauditsnap@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake for missing-audit test",
        )
        post_resp = self.client.post(
            f"/doctor/open/{entry.id}/create-no-intake/?lang=en",
        )
        self.assertEqual(post_resp.status_code, 302)
        doc = MedicalDocument.objects.get(queue_entry=entry)
        AuditEvent.objects.filter(
            medical_document_id=doc.id,
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
        ).delete()
        detail_resp = self.client.get(f"/doctor/{doc.id}/?lang=en")
        self.assertEqual(detail_resp.status_code, 422)
        self.assertIn(b"audit", detail_resp.content.lower())

    def test_open_by_queue_returns_404_when_published_document_not_accessible(
        self,
    ) -> None:
        """Another doctor must not open queue entry guarded by published document."""
        other = StaffUser.objects.create_user(
            username="doc-other-queue",
            email="doc.other.queue@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="NA", name="No Access Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="NoAccessQueue",
            date_of_birth=date(1994, 4, 4),
            phone="+48500333222",
            email="noaccessqueue@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="c" * 64,
        )
        MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=intake,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            created_by_user=self.doctor,
        )
        self.client.force_login(other)
        resp = self.client.get(f"/doctor/open/{entry.id}/?lang=en")
        self.assertEqual(resp.status_code, 404)

    def test_create_no_intake_shows_error_when_appointment_too_recent(self) -> None:
        self._login_doctor()
        clinic = ClinicSite.objects.create(code="TE", name="Too Early Create Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Pat",
            last_name="TooEarlyCreate",
            date_of_birth=date(1995, 5, 5),
            phone="+48500222111",
            email="tooearlycreate@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=timezone.now(),
            authorized_by=self.manager_user,
            reason="Patient delivered paper intake for early-create test.",
        )
        resp = self.client.post(f"/doctor/open/{entry.id}/create-no-intake/?lang=en")
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "create-no-intake", status_code=400)


class DoctorDetailHappyPathTests(TestCase):
    """Full data chain for the document detail view."""

    def setUp(self):
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="hp-doc",
            email="hp-doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        rec = StaffUser.objects.create_user(
            username="hp-rec",
            email="hp-rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")

        clinic = ClinicSite.objects.create(code="HP", name="HP Clinic")
        room = ConsultingRoom.objects.create(
            clinic_site=clinic, code="R1", name="Room 1"
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=rec,
        )
        patient = Patient.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            date_of_birth=date(1985, 6, 15),
            phone="+48500100200",
            email="jan@example.com",
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
            signature_sha256="a" * 64,
            body_map_data=[
                {"x": 0.22, "y": 0.35, "side": "front"},
                {"x": 0.72, "y": 0.4, "side": "back"},
            ],
        )
        self.doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        # Default HiDrive /incoming listing is empty in tests → real gate would return 424.
        gate_patcher = patch(
            "cogitomedica.doctor_views.check_external_pdf_gate",
            return_value=GateResult(
                True,
                (),
                None,
                skip_attachment_sync=False,
            ),
        )
        gate_patcher.start()
        self.addCleanup(gate_patcher.stop)

    def test_detail_happy_path_returns_200(self):
        self.client.force_login(self.doctor)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_detail_shows_hidrive_soft_warning_banner(
        self, mock_gate: MagicMock
    ) -> None:
        """Non-blocking HiDrive outage: gate passes but UI shows translated warning."""
        mock_gate.return_value = GateResult(
            True,
            (),
            "HiDrive folder read failed (test).",
            skip_attachment_sync=True,
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("HiDrive folder read failed (test).", resp.content.decode())

    def _publish_doc_for_detail(self, *, has_pending_revision: bool = False) -> None:
        now = timezone.now()
        MedicalDocumentVersion.objects.create(
            medical_document=self.doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/media/befund/rescan-test.pdf",
            publish_request_id=uuid4(),
            published_at=now,
            publish_locale="de-DE",
            published_by_user=self.doctor,
        )
        MedicalDocument.objects.filter(pk=self.doc.pk).update(
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            published_version_no=1,
            has_pending_revision=has_pending_revision,
            last_published_at=now,
        )
        self.doc.refresh_from_db()

    @patch("cogitomedica.doctor_views.create_attachment_records")
    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_published_without_revision_skips_hidrive_rescan(
        self, mock_gate: MagicMock, mock_sync: MagicMock
    ) -> None:
        self._publish_doc_for_detail(has_pending_revision=False)
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
        mock_gate.assert_not_called()
        mock_sync.assert_not_called()

    @patch("cogitomedica.doctor_views.create_attachment_records")
    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_pending_revision_rescans_and_syncs_matched_pdf(
        self, mock_gate: MagicMock, mock_sync: MagicMock
    ) -> None:
        self._publish_doc_for_detail(has_pending_revision=True)
        matched = MatchedIncomingFile(
            name="Cohen_Yaakov_CMBER2026FR272_20260721023036.pdf",
            path="/incoming/Cohen_Yaakov_CMBER2026FR272_20260721023036.pdf",
        )
        mock_gate.return_value = GateResult(
            True,
            (matched,),
            None,
            skip_attachment_sync=False,
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
        mock_gate.assert_called_once()
        mock_sync.assert_called_once()
        synced_doc, synced_files = mock_sync.call_args[0]
        self.assertEqual(synced_doc.id, self.doc.id)
        self.assertEqual(synced_files, (matched,))

    @patch("cogitomedica.doctor_views.create_attachment_records")
    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_pending_revision_gate_miss_does_not_block_or_prune(
        self, mock_gate: MagicMock, mock_sync: MagicMock
    ) -> None:
        self._publish_doc_for_detail(has_pending_revision=True)
        mock_gate.return_value = GateResult(
            False,
            (),
            "No matching PDF",
            skip_attachment_sync=False,
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
        mock_gate.assert_called_once()
        mock_sync.assert_not_called()

    def test_detail_panel_includes_body_map_image_url_and_stored_points(self):
        self.client.force_login(self.doctor)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert m is not None, "expected doctor-panel-data script in HTML"
        panel = json.loads(m.group(1))
        self.assertIn("bodyMapImageUrl", panel)
        self.assertIn("tablet/body.jpg", panel["bodyMapImageUrl"])
        pts = panel["context"]["intake_summary"]["body_map_data"]
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0]["side"], "front")
        self.assertEqual(panel["context"]["intake_summary"]["reception_note"], "")
        self.assertIn("intake_summary_reception_note_heading", panel["ui"])
        self.assertIn('id="intake-reception-note"', html)
        self.assertRegex(html, r'id="intake-reception-note"[^>]*\bhidden\b')

    def test_detail_panel_includes_reception_note_below_anamnesis_payload(self):
        note = "Patient besorgt wegen Stellen auf der Kopfhaut."
        PatientIntakeForm.objects.filter(pk=self.doc.intake_form_id).update(
            reception_note=note
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert m is not None, "expected doctor-panel-data script in HTML"
        panel = json.loads(m.group(1))
        self.assertEqual(panel["context"]["intake_summary"]["reception_note"], note)
        self.assertIn('id="intake-reception-note"', html)
        self.assertIn(note, html)

    def test_pending_revision_detail_panel_includes_reception_note(self):
        note = "Patient besorgt wegen Stellen auf der Kopfhaut."
        PatientIntakeForm.objects.filter(pk=self.doc.intake_form_id).update(
            reception_note=note
        )
        self._publish_doc_for_detail(has_pending_revision=True)
        MedicalDocumentVersion.objects.create(
            medical_document=self.doc,
            version_no=2,
            version_status=DocVersionStatus.DRAFT,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1, "authoring_locale": "de-DE"},
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('id="intake-summary"', html)
        self.assertIn('id="befund-form"', html)
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert m is not None, "expected doctor-panel-data script in HTML"
        panel = json.loads(m.group(1))
        self.assertTrue(panel["context"]["has_pending_revision"])
        self.assertEqual(panel["context"]["status"], MedicalDocStatus.PUBLISHED)
        self.assertEqual(panel["context"]["intake_summary"]["reception_note"], note)
        self.assertTrue(
            (panel["ui"].get("intake_summary_reception_note_heading") or "").strip()
        )
        self.assertIn('id="intake-reception-note"', html)
        self.assertIn(note, html)

    @patch(
        "cogitomedica.doctor_views.acquire_document_lock",
        return_value=(True, None),
    )
    def test_detail_panel_current_version_includes_hidrive_sms_flags(
        self,
        _mock_lock: MagicMock,
    ) -> None:
        """Panel JSON must expose delivery flags used by ``refreshRevisionUi`` / revoke."""
        now = timezone.now()
        MedicalDocumentVersion.objects.create(
            medical_document=self.doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/media/befund/doctor-panel-revoke.pdf",
            publish_request_id=uuid4(),
            published_at=now,
            publish_locale="de-DE",
            published_by_user=self.doctor,
            hidrive_sent=True,
            hidrive_sent_at=now,
            sms_sent=False,
            sms_sent_at=None,
        )
        MedicalDocument.objects.filter(pk=self.doc.pk).update(
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            published_version_no=1,
            has_pending_revision=False,
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/?lang=pl")
        self.assertEqual(resp.status_code, 200)
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            resp.content.decode(),
            re.DOTALL,
        )
        assert m is not None
        panel = json.loads(m.group(1))
        cv = panel["context"]["current_version"]
        self.assertTrue(cv["hidrive_sent"])
        self.assertFalse(cv["sms_sent"])
        self.assertIsNone(cv.get("revoked_at"))

    @patch(
        "cogitomedica.doctor_views.acquire_document_lock",
        return_value=(True, None),
    )
    def test_detail_panel_current_version_includes_revoked_at_when_revoked(
        self,
        _mock_lock: MagicMock,
    ) -> None:
        """Revoked publication: ``revoked_at`` in panel drives revoked banner in JS."""
        now = timezone.now()
        MedicalDocumentVersion.objects.create(
            medical_document=self.doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/media/befund/doctor-panel-revoked.pdf",
            publish_request_id=uuid4(),
            published_at=now,
            publish_locale="de-DE",
            published_by_user=self.doctor,
            hidrive_sent=True,
            hidrive_sent_at=now,
            sms_sent=True,
            sms_sent_at=now,
            revoked_at=now,
        )
        MedicalDocument.objects.filter(pk=self.doc.pk).update(
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            published_version_no=1,
            has_pending_revision=False,
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/?lang=pl")
        self.assertEqual(resp.status_code, 200)
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            resp.content.decode(),
            re.DOTALL,
        )
        assert m is not None
        panel = json.loads(m.group(1))
        cv = panel["context"]["current_version"]
        self.assertIsNotNone(cv.get("revoked_at"))

    def test_detail_returns_423_when_locked_by_another_doctor(self):
        other = StaffUser.objects.create_user(
            username="hp-doc-2",
            email="hp-doc-2@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        dq = self.doc.queue_entry.daily_queue
        dq.assigned_doctor = other
        dq.save(update_fields=["assigned_doctor", "updated_at"])
        self.doc.locked_by_user = self.doctor
        self.doc.locked_at = timezone.now()
        self.doc.save(update_fields=["locked_by_user", "locked_at", "updated_at"])

        self.client.force_login(other)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 423)

    def test_second_doctor_can_open_draft_without_queue_assignment(self):
        dq = self.doc.queue_entry.daily_queue
        dq.assigned_doctor = None
        dq.save(update_fields=["assigned_doctor", "updated_at"])
        other = StaffUser.objects.create_user(
            username="hp-doc-shared",
            email="hp-doc-shared@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        self.client.force_login(other)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)

    @patch(
        "cogitomedica.doctor_views.check_external_pdf_gate",
        return_value=GateResult(
            False,
            (),
            "GATE_BLOCKED",
            skip_attachment_sync=False,
        ),
    )
    def test_detail_returns_424_when_external_pdf_gate_blocks(
        self,
        _mock_gate: MagicMock,
    ) -> None:
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 424)
        self.assertIn("GATE_BLOCKED", resp.content.decode())

    @patch(
        "cogitomedica.doctor_views.check_external_pdf_gate",
        return_value=GateResult(
            False,
            (),
            "GATE_BLOCKED",
            skip_attachment_sync=False,
        ),
    )
    def test_detail_bypasses_external_pdf_gate_for_published_document(
        self,
        mock_gate: MagicMock,
    ) -> None:
        self.doc.status = MedicalDocStatus.PUBLISHED
        self.doc.published_version_no = 1
        self.doc.current_version_no = 1
        self.doc.save(
            update_fields=[
                "status",
                "published_version_no",
                "current_version_no",
                "updated_at",
            ]
        )
        MedicalDocumentVersion.objects.create(
            medical_document=self.doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            publish_request_id=uuid4(),
            published_at=timezone.now(),
            publish_locale="de-DE",
            published_by_user=self.doctor,
        )

        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")

        self.assertEqual(resp.status_code, 200)
        mock_gate.assert_not_called()

    @patch(
        "cogitomedica.doctor_views.get_medical_document_context",
        return_value={"intake_summary": {"patient": {}}},
    )
    def test_detail_returns_404_when_intake_patient_id_missing(
        self,
        _mock_ctx: MagicMock,
    ) -> None:
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 404)


class DoctorListScopeAndPreviewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="scope-doc",
            email="scope-doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.other_doctor = StaffUser.objects.create_user(
            username="scope-doc-other",
            email="scope-doc-other@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.other_doctor, "Doctor")
        self.reception = StaffUser.objects.create_user(
            username="scope-rec",
            email="scope-rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.manager_user = StaffUser.objects.create_user(
            username="scope-mgr",
            email="scope-mgr@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.manager_user, "Manager")
        self.clinic = ClinicSite.objects.create(code="SC", name="Scope Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="R1",
            name="Room 1",
        )

    def _create_published_document(
        self,
        *,
        patient_last_name: str,
        published_by: StaffUser,
        queue_assigned_doctor: StaffUser | None = None,
        source_type: str = "DIGITAL_INTAKE",
    ) -> MedicalDocument:
        patient = Patient.objects.create(
            first_name="Jan",
            last_name=patient_last_name,
            date_of_birth=date(1985, 6, 15),
            phone=f"+48500{uuid4().int % 1000000:06d}",
            email=f"{patient_last_name.lower()}@example.com",
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date()
            + timedelta(days=DailyQueue.objects.count()),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            assigned_doctor=queue_assigned_doctor,
            created_by_user=self.reception,
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
            body_map_data=[],
        )
        doc = MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=intake,
            source_type=source_type,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            published_version_no=1,
            created_by_user=self.reception,
            updated_by_user=published_by,
        )
        MedicalDocumentVersion.objects.create(
            medical_document=doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/media/befund/test.pdf",
            publish_request_id=uuid4(),
            published_at=timezone.now(),
            publish_locale="de-DE",
            published_by_user=published_by,
        )
        return doc

    def test_default_list_keeps_published_document_visible_for_publishing_doctor(self):
        published_doc = self._create_published_document(
            patient_last_name="HistoryVisible",
            published_by=self.doctor,
            queue_assigned_doctor=self.other_doctor,
        )
        self.client.force_login(self.doctor)

        response = self.client.get("/doctor/")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(_stored_patient_name("HistoryVisible"), html)
        self.assertIn(
            f"/api/v1/medical-documents/{published_doc.id}/preview-pdf",
            html,
        )

    def test_list_preview_uses_medical_document_preview_for_external_source(
        self,
    ) -> None:
        ext_doc = self._create_published_document(
            patient_last_name="ExternalListPreview",
            published_by=self.doctor,
            queue_assigned_doctor=self.other_doctor,
            source_type="EXTERNAL_UPLOAD",
        )
        self.client.force_login(self.doctor)
        response = self.client.get("/doctor/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(_stored_patient_name("ExternalListPreview"), html)
        self.assertIn(
            f"/api/v1/medical-documents/{ext_doc.id}/preview-pdf",
            html,
        )
        self.assertNotIn(
            f"/api/v1/medical-documents/{ext_doc.id}/external-upload/preview-pdf",
            html,
        )

    def test_doctor_list_shows_only_own_published_results(self):
        matching_doc = self._create_published_document(
            patient_last_name="PublishedByMe",
            published_by=self.doctor,
            queue_assigned_doctor=self.other_doctor,
        )
        self._create_published_document(
            patient_last_name="PublishedByOther",
            published_by=self.other_doctor,
            queue_assigned_doctor=self.other_doctor,
        )
        self.client.force_login(self.doctor)
        response = self.client.get("/doctor/")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(_stored_patient_name("PublishedByMe"), html)
        self.assertNotIn(_stored_patient_name("PublishedByOther"), html)
        self.assertIn(
            f"/api/v1/medical-documents/{matching_doc.id}/preview-pdf",
            html,
        )

    def test_manager_published_by_filter_limits_list(self):
        self._create_published_document(
            patient_last_name="PublishedByMe",
            published_by=self.doctor,
            queue_assigned_doctor=self.other_doctor,
        )
        self._create_published_document(
            patient_last_name="PublishedByOther",
            published_by=self.other_doctor,
            queue_assigned_doctor=self.other_doctor,
        )
        self.client.force_login(self.manager_user)
        response = self.client.get(f"/doctor/?published_by_user_id={self.doctor.id}")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(_stored_patient_name("PublishedByMe"), html)
        self.assertNotIn(_stored_patient_name("PublishedByOther"), html)

    def test_scope_in_revision_filters_pending_revision_rows(self) -> None:
        rev_doc = self._create_published_document(
            patient_last_name="InRevisionOnly",
            published_by=self.doctor,
            queue_assigned_doctor=self.doctor,
        )
        MedicalDocument.objects.filter(pk=rev_doc.pk).update(has_pending_revision=True)
        self._create_published_document(
            patient_last_name="PublishedStable",
            published_by=self.doctor,
            queue_assigned_doctor=self.doctor,
        )
        self.client.force_login(self.manager_user)

        response = self.client.get("/doctor/?scope=in_revision")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(_stored_patient_name("InRevisionOnly"), html)
        self.assertNotIn(_stored_patient_name("PublishedStable"), html)
        self.assertIn('option value="in_revision" selected', html)


class DoctorRbacIdorHtmlTests(TestCase):
    """IDOR matrix §6.3: HTML paths H1–H2."""

    def setUp(self) -> None:
        from apps.medical.tests.test_api import MedicalApiTests

        MedicalApiTests.setUp(self)

        self.doctor_b = StaffUser.objects.create_user(
            username="html-idor-b",
            email="html.idor.b@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_b, "Doctor")
        self.queue_entry.daily_queue.assigned_doctor = self.doctor_b
        self.queue_entry.daily_queue.save(
            update_fields=["assigned_doctor", "updated_at"]
        )

    def _publish_as_doctor_a(self) -> str:
        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        self.client.force_login(self.doctor_user)
        create_resp = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                }
            ),
            content_type="application/json",
        )
        mid = create_resp.json()["medical_document_id"]
        self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data=json.dumps(
                {"medical_payload_schema_version": 1, "medical_payload": payload}
            ),
            content_type="application/json",
        )
        self.client.post(
            f"/api/v1/medical-documents/{mid}/publish",
            data=json.dumps(
                {"publish_request_id": str(uuid4()), "publish_locale": "de-DE"}
            ),
            content_type="application/json",
        )
        return mid

    def test_h1_doctor_b_document_detail_returns_404(self) -> None:
        mid = self._publish_as_doctor_a()
        self.client.force_login(self.doctor_b)
        resp = self.client.get(f"/doctor/{mid}/")
        self.assertEqual(resp.status_code, 404)

    def test_h2_open_queue_does_not_expose_foreign_published_document(self) -> None:
        mid = self._publish_as_doctor_a()
        self.client.force_login(self.doctor_b)
        resp = self.client.get(f"/doctor/open/{self.queue_entry.id}/")
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn(str(mid), resp.content.decode())

    def test_h2_open_queue_writes_access_denied_audit(self) -> None:
        """HTML open-by-queue audits denial before 404 (same as API detail)."""
        mid = self._publish_as_doctor_a()
        AuditEvent.objects.filter(event_type="MEDICAL_DOCUMENT_ACCESS_DENIED").delete()
        self.client.force_login(self.doctor_b)
        resp = self.client.get(f"/doctor/open/{self.queue_entry.id}/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="MEDICAL_DOCUMENT_ACCESS_DENIED",
                medical_document_id=mid,
            ).count(),
            1,
        )


class DoctorListSortUxTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="sort-ux-doc",
            email="sort.ux@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        clinic = ClinicSite.objects.create(code="SUX", name="Sort UX Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        rec = StaffUser.objects.create_user(
            username="sort-ux-rec",
            email="sort.ux.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=rec,
        )
        patient = Patient.objects.create(
            first_name="Sort",
            last_name="UxPatient",
            date_of_birth=date(1985, 1, 1),
            phone="+48500999001",
            email="sortux@example.com",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=rec,
        )
        session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=rec,
        )
        self.intake = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )

    def test_filter_submit_preserves_sort_and_order(self) -> None:
        self.client.force_login(self.doctor)
        response = self.client.get(
            "/doctor/",
            {"sort": "patient", "order": "asc", "status": "DRAFT"},
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('name="sort"', html)
        self.assertIn('value="patient"', html)
        self.assertIn('name="order"', html)
        self.assertIn('value="asc"', html)

    def test_sort_link_patient_toggles_order(self) -> None:
        self.client.force_login(self.doctor)
        first = self.client.get("/doctor/", {"sort": "patient", "order": "asc"})
        self.assertEqual(first.status_code, 200)
        second = self.client.get("/doctor/", {"sort": "patient", "order": "desc"})
        self.assertEqual(second.status_code, 200)
        html = second.content.decode()
        self.assertIn("arrow_downward", html)


class DoctorListStatusDisplayTests(TestCase):
    def test_unknown_status_code_returns_raw_value(self) -> None:
        from cogitomedica.doctor_views import _doctor_list_status_display

        self.assertEqual(
            _doctor_list_status_display("CUSTOM_STAGE", {}, {}),
            "CUSTOM_STAGE",
        )
