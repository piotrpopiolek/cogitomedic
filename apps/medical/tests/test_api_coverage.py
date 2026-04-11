"""HTTP-contract tests for untested medical API endpoints."""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    DocVersionStatus,
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

    def _doc_url(self, suffix: str = "") -> str:
        return f"{BASE}medical-documents/{self.medical_doc.id}{suffix}"

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
        self._login_doctor()
        r = self.client.get(self._doc_url("/preview-pdf"))
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
        self._login_doctor()
        r = self.client.get(self._doc_url("/preview-pdf") + "?form_locale=en-GB")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")

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

    def test_draft_put_returns_423_when_refresh_lock_fails_after_save(self):
        """If refresh_document_lock loses a race, API must roll back and report 423."""
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
        }
        self._login_doctor()
        with patch("apps.medical.api_views.refresh_document_lock", return_value=False):
            r = self.client.put(
                self._doc_url("/draft"),
                data=json.dumps(body),
                content_type="application/json",
            )
        self.assertEqual(r.status_code, 423)
        self.assertIn("locked_by_username", r.json())

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
