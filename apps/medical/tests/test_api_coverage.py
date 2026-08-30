"""HTTP-contract tests for untested medical API endpoints."""

from __future__ import annotations

import json
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from pypdf import PdfWriter

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
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
from apps.users.models import StaffUser

BASE = "/api/v1/"


class Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="cov-doctor",
            email="d@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.reception = StaffUser.objects.create_user(
            username="cov-rec",
            email="r@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.manager = StaffUser.objects.create_user(
            username="cov-mgr",
            email="m@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.manager, "Manager")

        clinic = ClinicSite.objects.create(code="MC", name="MC Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="M1", name="M1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="Test",
            last_name="Med",
            date_of_birth=date(1990, 1, 1),
            phone="+48500100201",
            email="med@example.com",
        )
        qe = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception,
        )
        sess = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=sess,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )
        self.medical_doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )

    # -- helpers -------------------------------------------------

    def _login_doctor(self):
        self.client.login(username="cov-doctor", password="x")

    def _login_reception(self):
        self.client.login(username="cov-rec", password="x")

    def _login_manager(self):
        self.client.login(username="cov-mgr", password="x")

    def _doc_url(self, suffix: str = "") -> str:
        return f"{BASE}medical-documents/{self.medical_doc.id}{suffix}"

    def _start_edit_session(self) -> dict:
        self._login_doctor()
        response = self.client.post(
            self._doc_url("/edit-session"),
            data=json.dumps({"purpose": "edit"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _preview_draft_pdf(self, *, query: str = "") -> object:
        sess = self._start_edit_session()
        q = (
            f"?source=draft&expected_draft_revision={sess['draft_revision']}"
            + (f"&{query.lstrip('?&')}" if query else "")
        )
        return self.client.get(
            self._doc_url("/preview-pdf") + q,
            HTTP_X_EDIT_SESSION_TOKEN=sess["edit_session_token"],
        )

    # =============================================================
    # 1. medical_document_revoke_view  (POST …/<uuid>/revoke)
    # =============================================================

    def test_revoke_wrong_method_returns_405(self):
        self._login_doctor()
        r = self.client.get(self._doc_url("/revoke"))
        self.assertEqual(r.status_code, 405)

    def test_revoke_wrong_role_returns_403(self):
        self._login_reception()
        r = self.client.post(self._doc_url("/revoke"))
        self.assertEqual(r.status_code, 403)

    def test_revoke_nonexistent_doc_returns_404(self):
        self._login_doctor()
        url = f"{BASE}medical-documents/{uuid4()}/revoke"
        r = self.client.post(url)
        self.assertEqual(r.status_code, 404)

    def _publish_default_doc_with_delivery(
        self,
        *,
        hidrive_sent: bool = True,
        sms_sent: bool = True,
    ) -> MedicalDocumentVersion:
        """Turn ``self.medical_doc`` into PUBLISHED v1 for revoke / panel contract tests."""
        doc = self.medical_doc
        now = timezone.now()
        ver = MedicalDocumentVersion.objects.create(
            medical_document=doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/media/befund/api-coverage-revoke.pdf",
            publish_request_id=uuid4(),
            published_at=now,
            publish_locale="de-DE",
            published_by_user=self.doctor,
            hidrive_sent=hidrive_sent,
            hidrive_sent_at=now if hidrive_sent else None,
            sms_sent=sms_sent,
            sms_sent_at=now if sms_sent else None,
        )
        MedicalDocument.objects.filter(pk=doc.pk).update(
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            published_version_no=1,
            has_pending_revision=False,
        )
        return ver

    @patch("apps.medical.services._try_delete_file")
    def test_revoke_post_doctor_returns_200_when_hidrive_and_sms_sent(
        self, _mock_del: object
    ) -> None:
        """Doctor panel POST …/revoke: happy path when delivery flags allow revoke."""
        self._publish_default_doc_with_delivery()
        self._login_doctor()
        r = self.client.post(self._doc_url("/revoke"))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertIn("revoked_at", body)
        self.assertIsNotNone(body["revoked_at"])

    def test_revoke_post_doctor_returns_400_when_sms_not_sent(self) -> None:
        """``revoke_document_version`` rejects revoke until SMS (and HiDrive) are complete."""
        self._publish_default_doc_with_delivery(hidrive_sent=True, sms_sent=False)
        self._login_doctor()
        r = self.client.post(self._doc_url("/revoke"))
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(
            r.json().get("error_key"),
            "other.domain.revoke_requires_full_delivery",
        )

    # =============================================================
    # 2. medical_document_audit_trail_view  (GET …/<uuid>/audit-trail)
    # =============================================================

    def test_audit_trail_wrong_method_returns_405(self):
        self._login_doctor()
        r = self.client.post(self._doc_url("/audit-trail"))
        self.assertEqual(r.status_code, 405)

    def test_audit_trail_wrong_role_returns_403(self):
        self._login_reception()
        r = self.client.get(self._doc_url("/audit-trail"))
        self.assertEqual(r.status_code, 403)

    def test_audit_trail_nonexistent_doc_returns_404(self):
        self._login_doctor()
        url = f"{BASE}medical-documents/{uuid4()}/audit-trail"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)

    def test_audit_trail_happy_path_returns_200(self):
        self._login_doctor()
        r = self.client.get(self._doc_url("/audit-trail"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("items", body)
        self.assertIn("pagination", body)
        self.assertIsInstance(body["items"], list)
        self.assertIsInstance(body["pagination"]["total"], int)

    def test_audit_trail_ref_fallback_after_set_null(self):
        """After actor_user FK is NULLed, actor_user_id is still
        returned from metadata._ref (compliance requirement)."""
        actor_id = str(self.doctor.id)
        evt = AuditEvent.objects.create(
            event_type="TEST_REF_FALLBACK",
            actor_user=self.doctor,
            medical_document=self.medical_doc,
            metadata={
                "_ref": {
                    "actor_user_id": actor_id,
                    "medical_document_id": str(self.medical_doc.id),
                }
            },
        )
        # Simulate SET_NULL (as if the StaffUser row was deleted)
        AuditEvent.objects.filter(id=evt.id).update(actor_user=None)

        self._login_doctor()
        r = self.client.get(self._doc_url("/audit-trail"))
        self.assertEqual(r.status_code, 200)
        items = r.json()["items"]
        matched = [i for i in items if i["id"] == str(evt.id)]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["actor_user_id"], actor_id)

    # =============================================================
    # 3. medical_documents_view  (POST /medical-documents)
    # =============================================================

    def test_documents_post_wrong_role_returns_403(self):
        self._login_reception()
        r = self.client.post(
            f"{BASE}medical-documents",
            data=json.dumps({"queue_entry_id": str(uuid4())}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    def test_documents_post_invalid_json_returns_400(self):
        self._login_doctor()
        r = self.client.post(
            f"{BASE}medical-documents",
            data="NOT-JSON",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_documents_get_wrong_method_returns_405(self):
        self._login_doctor()
        r = self.client.delete(f"{BASE}medical-documents")
        self.assertEqual(r.status_code, 405)

    def test_documents_get_as_manager_returns_200(self):
        self._login_manager()
        r = self.client.get(f"{BASE}medical-documents")
        self.assertEqual(r.status_code, 200)
        self.assertIn("items", r.json())

    def test_medical_document_detail_get_as_manager_returns_200(self):
        self._login_manager()
        r = self.client.get(self._doc_url(""))
        self.assertEqual(r.status_code, 200)
        self.assertIn("id", r.json())

    def test_documents_post_validation_error_returns_400(self):
        self._login_doctor()
        r = self.client.post(
            f"{BASE}medical-documents",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.json())

    def test_documents_post_intake_not_submitted_returns_400(self):
        """create_or_get rejects intake that is not SUBMITTED (clinical safety)."""
        qe = QueueEntry.objects.create(
            daily_queue=self.medical_doc.queue_entry.daily_queue,
            patient=self.medical_doc.queue_entry.patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=99,
            created_by_user=self.reception,
        )
        sess = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=sess,
            form_status=IntakeStatus.IN_PROGRESS,
            signature_sha256="b" * 64,
        )
        self._login_doctor()
        r = self.client.post(
            f"{BASE}medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(qe.id),
                    "intake_form_id": str(intake.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_documents_post_intake_wrong_queue_entry_returns_400(self):
        """Intake form must belong to the queue entry in the request."""
        dq = self.medical_doc.queue_entry.daily_queue
        other_qe = QueueEntry.objects.create(
            daily_queue=dq,
            patient=self.medical_doc.queue_entry.patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=98,
            created_by_user=self.reception,
        )
        other_sess = PatientFormSession.objects.create(
            queue_entry=other_qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception,
        )
        other_intake = PatientIntakeForm.objects.create(
            queue_entry=other_qe,
            session=other_sess,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="c" * 64,
        )
        self._login_doctor()
        r = self.client.post(
            f"{BASE}medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.medical_doc.queue_entry.id),
                    "intake_form_id": str(other_intake.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    # =============================================================
    # 3b. medical_document_preview_pdf_view
    # =============================================================

    def test_preview_pdf_wrong_method_returns_405(self):
        self._login_doctor()
        r = self.client.post(self._doc_url("/preview-pdf"))
        self.assertEqual(r.status_code, 405)

    def test_preview_pdf_no_version_returns_404(self):
        self._login_doctor()
        self.assertEqual(self.medical_doc.versions.count(), 0)
        r = self.client.get(self._doc_url("/preview-pdf"))
        self.assertEqual(r.status_code, 404)

    def test_preview_pdf_happy_path_returns_pdf(self):
        MedicalDocumentVersion.objects.create(
            medical_document=self.medical_doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            pdf_generation_status=PdfStatus.PENDING,
            medical_payload_schema_version=1,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        r = self._preview_draft_pdf()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", r.content[:8])

    def test_preview_pdf_accepts_form_locale_query(self):
        MedicalDocumentVersion.objects.create(
            medical_document=self.medical_doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            pdf_generation_status=PdfStatus.PENDING,
            medical_payload_schema_version=1,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        r = self._preview_draft_pdf(query="form_locale=en-GB")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch(
        "apps.medical.pdf_builder.download_external_pdf",
        side_effect=RuntimeError("simulated HiDrive failure"),
    )
    def test_preview_pdf_returns_befund_when_external_download_raises(self, _mock_dl):
        MedicalDocumentVersion.objects.create(
            medical_document=self.medical_doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            pdf_generation_status=PdfStatus.PENDING,
            medical_payload_schema_version=1,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/x.pdf",
            original_filename="x.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        r = self._preview_draft_pdf()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", r.content[:8])
        warn = (r.get("X-Befund-Preview-Warning") or "").lower()
        self.assertIn("external_pdf_download_failed", warn)

    # =============================================================
    # 3b2. External HiDrive PDF attachments API
    # =============================================================

    @staticmethod
    def _minimal_pdf_bytes() -> bytes:
        w = PdfWriter()
        w.add_blank_page(width=200, height=200)
        buf = BytesIO()
        w.write(buf)
        return buf.getvalue()

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_external_pdfs_get_empty_list(self) -> None:
        from apps.integrations.hidrive import client as hidrive_client

        hidrive_client._MockHiDriveAdapter.reset_test_state()
        self._login_doctor()
        r = self.client.get(self._doc_url("/external-pdfs"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("items"), [])

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_external_pdfs_get_with_attachment(self) -> None:
        from apps.integrations.hidrive import client as hidrive_client

        hidrive_client._MockHiDriveAdapter.reset_test_state()
        pdf = self._minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Test_Med.pdf",
                    "path": "/incoming/Test_Med.pdf",
                    "size": len(pdf),
                    "mtime": None,
                }
            ],
        )
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Test_Med.pdf", pdf)
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Test_Med.pdf",
            original_filename="Test_Med.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        r = self.client.get(self._doc_url("/external-pdfs"))
        self.assertEqual(r.status_code, 200)
        items = r.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["filename"], "Test_Med.pdf")
        self.assertEqual(items[0]["status"], "MATCHED")

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_external_pdf_content_get_returns_pdf(self) -> None:
        from apps.integrations.hidrive import client as hidrive_client

        hidrive_client._MockHiDriveAdapter.reset_test_state()
        pdf = self._minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Test_Med.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Test_Med.pdf",
            original_filename="Test_Med.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        r = self.client.get(self._doc_url(f"/external-pdfs/{att.id}/content"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", r.content[:8])
        self.assertEqual(
            (r.get("X-Frame-Options") or "").upper(),
            "SAMEORIGIN",
            msg="Doctor panel embeds this URL in an iframe (avoid blob: for large PDFs).",
        )

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_external_pdf_content_rejected_returns_410(self) -> None:
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/rejected_Test_Med.pdf",
            original_filename="rejected_Test_Med.pdf",
            status=ExternalPdfStatus.REJECTED,
        )
        self._login_doctor()
        r = self.client.get(self._doc_url(f"/external-pdfs/{att.id}/content"))
        self.assertEqual(r.status_code, 410)

    @override_settings(DEBUG=False, HIDRIVE_USE_MOCK="1")
    @patch(
        "apps.medical.api_views.download_external_pdf",
        side_effect=RuntimeError("hidrive down"),
    )
    def test_external_pdf_content_infra_error_returns_502(
        self, _mock_dl: object
    ) -> None:
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Test_Med.pdf",
            original_filename="Test_Med.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        r = self.client.get(self._doc_url(f"/external-pdfs/{att.id}/content"))
        self.assertEqual(r.status_code, 502)
        self.assertIn("error", r.json())

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_external_pdf_content_corrupt_returns_422(self) -> None:
        from apps.integrations.hidrive import client as hidrive_client

        hidrive_client._MockHiDriveAdapter.reset_test_state()
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Test_Med.pdf",
            original_filename="Test_Med.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        with patch(
            "apps.medical.api_views.download_external_pdf",
            side_effect=ExternalPdfCorruptError("x"),
        ):
            r = self.client.get(self._doc_url(f"/external-pdfs/{att.id}/content"))
        self.assertEqual(r.status_code, 422)
        self.assertIn("error", r.json())

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_external_pdf_reject_post_updates_status(self) -> None:
        from apps.integrations.hidrive import client as hidrive_client

        hidrive_client._MockHiDriveAdapter.reset_test_state()
        pdf = self._minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Test_Med.pdf",
                    "path": "/incoming/Test_Med.pdf",
                    "size": len(pdf),
                    "mtime": None,
                }
            ],
        )
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Test_Med.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Test_Med.pdf",
            original_filename="Test_Med.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        r = self.client.post(
            self._doc_url(f"/external-pdfs/{att.id}/reject"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.REJECTED)
        self.assertIn("rejected_", att.hidrive_remote_path)

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch(
        "apps.medical.pdf_builder.download_external_pdf",
        side_effect=ExternalPdfCorruptError("x"),
    )
    def test_preview_pdf_sets_warning_header_on_corrupt_external(
        self,
        _mock_dl: object,
    ) -> None:
        MedicalDocumentVersion.objects.create(
            medical_document=self.medical_doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            pdf_generation_status=PdfStatus.PENDING,
            medical_payload_schema_version=1,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/x.pdf",
            original_filename="x.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        r = self._preview_draft_pdf()
        self.assertEqual(r.status_code, 200)
        warn = (r.get("X-Befund-Preview-Warning") or "").lower()
        self.assertIn("external_pdf_corrupt", warn)

    def test_external_pdfs_not_found_returns_404(self) -> None:
        self._login_doctor()
        r = self.client.get(f"{BASE}medical-documents/{uuid4()}/external-pdfs")
        self.assertEqual(r.status_code, 404)

    def test_external_pdf_content_wrong_method_returns_405(self) -> None:
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/x.pdf",
            original_filename="x.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        r = self.client.post(self._doc_url(f"/external-pdfs/{att.id}/content"))
        self.assertEqual(r.status_code, 405)

    def test_external_pdf_content_doc_not_found_returns_404(self) -> None:
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/x.pdf",
            original_filename="x.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        r = self.client.get(
            f"{BASE}medical-documents/{uuid4()}/external-pdfs/{att.id}/content"
        )
        self.assertEqual(r.status_code, 404)

    def test_external_pdf_content_attachment_not_found_returns_404(self) -> None:
        self._login_doctor()
        r = self.client.get(
            self._doc_url(f"/external-pdfs/{uuid4()}/content"),
        )
        self.assertEqual(r.status_code, 404)

    def test_external_pdf_reject_doc_not_found_returns_404(self) -> None:
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/x.pdf",
            original_filename="x.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        r = self.client.post(
            f"{BASE}medical-documents/{uuid4()}/external-pdfs/{att.id}/reject",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)

    def test_external_pdf_reject_already_rejected_returns_200(self) -> None:
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/rejected_x.pdf",
            original_filename="rejected_x.pdf",
            status=ExternalPdfStatus.REJECTED,
        )
        self._login_doctor()
        r = self.client.post(
            self._doc_url(f"/external-pdfs/{att.id}/reject"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), ExternalPdfStatus.REJECTED)

    @override_settings(HIDRIVE_USE_MOCK="1")
    @patch(
        "apps.medical.api_views.reject_external_pdf",
        side_effect=RuntimeError("HiDrive move failed"),
    )
    def test_external_pdf_reject_hidrive_error_returns_502(
        self,
        _mock_reject: object,
    ) -> None:
        from apps.integrations.hidrive import client as hidrive_client

        hidrive_client._MockHiDriveAdapter.reset_test_state()
        pdf = self._minimal_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file("/incoming/Test_Med.pdf", pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=self.medical_doc,
            hidrive_remote_path="/incoming/Test_Med.pdf",
            original_filename="Test_Med.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        self._login_doctor()
        r = self.client.post(
            self._doc_url(f"/external-pdfs/{att.id}/reject"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 502)

    def test_external_pdfs_wrong_method_returns_405(self) -> None:
        self._login_doctor()
        r = self.client.post(self._doc_url("/external-pdfs"))
        self.assertEqual(r.status_code, 405)

    def test_external_pdfs_reception_returns_403(self) -> None:
        self._login_reception()
        r = self.client.get(self._doc_url("/external-pdfs"))
        self.assertEqual(r.status_code, 403)

    # =============================================================
    # 3c. medical_document_draft_view — encoding / validation / lock race
    # =============================================================

    def test_draft_put_invalid_utf8_returns_400(self):
        self._login_doctor()
        r = self.client.put(
            self._doc_url("/draft"),
            data=b"\xff\xfe not utf-8",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_draft_put_validation_error_returns_400(self):
        self._login_doctor()
        r = self.client.put(
            self._doc_url("/draft"),
            data=json.dumps({"medical_payload_schema_version": 1}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.json())

    def test_draft_put_returns_423_when_edit_session_expired(self):
        """Expired lock → write gate returns 423 edit_session_expired (no silent save)."""
        sess = self._start_edit_session()
        MedicalDocument.objects.filter(pk=self.medical_doc.pk).update(
            locked_at=timezone.now() - timedelta(hours=48)
        )
        body = {
            "medical_payload_schema_version": 1,
            "medical_payload": {
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "lesions": [],
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
            "edit_session_token": sess["edit_session_token"],
            "expected_draft_revision": sess["draft_revision"],
            "draft_save_request_id": str(uuid4()),
        }
        r = self.client.put(
            self._doc_url("/draft"),
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 423)
        self.assertEqual(r.json().get("error_key"), "edit_session_expired")

    # =============================================================
    # 3d. medical_document_publish_view — bad body
    # =============================================================

    def test_publish_post_invalid_utf8_returns_400(self):
        self._login_doctor()
        r = self.client.post(
            self._doc_url("/publish"),
            data=b"\xff invalid",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_publish_post_validation_error_returns_400(self):
        self._login_doctor()
        r = self.client.post(
            self._doc_url("/publish"),
            data=json.dumps({"publish_request_id": str(uuid4())}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("details", r.json())

    # =============================================================
    # 4. medical_document_detail_view  (GET …/<uuid>)
    # =============================================================

    def test_detail_wrong_role_returns_403(self):
        self._login_reception()
        r = self.client.get(self._doc_url(""))
        self.assertEqual(r.status_code, 403)

    def test_detail_wrong_method_returns_405(self):
        self._login_doctor()
        r = self.client.post(self._doc_url(""))
        self.assertEqual(r.status_code, 405)

    # =============================================================
    # 5. medical_document_versions_view  (GET …/<uuid>/versions)
    # =============================================================

    def test_versions_wrong_role_returns_403(self):
        self._login_reception()
        r = self.client.get(self._doc_url("/versions"))
        self.assertEqual(r.status_code, 403)

    def test_versions_wrong_method_returns_405(self):
        self._login_doctor()
        r = self.client.post(self._doc_url("/versions"))
        self.assertEqual(r.status_code, 405)

    # =============================================================
    # 6. medical_document_version_detail_view
    #    (GET /medical-document-versions/<uuid>)
    # =============================================================

    def test_version_detail_wrong_role_returns_403(self):
        self._login_reception()
        url = f"{BASE}medical-document-versions/{uuid4()}"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 403)

    def test_version_detail_wrong_method_returns_405(self):
        self._login_doctor()
        url = f"{BASE}medical-document-versions/{uuid4()}"
        r = self.client.post(url)
        self.assertEqual(r.status_code, 405)
