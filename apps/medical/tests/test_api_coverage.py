"""HTTP-contract tests for untested medical API endpoints."""

from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import MedicalDocStatus, MedicalDocument
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
