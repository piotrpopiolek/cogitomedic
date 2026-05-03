"""HTTP branch coverage for paper-intake medical API endpoints (diff-cover)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.medical.services import authorize_paper_intake
from apps.intake.models import IntakeStatus, PatientIntakeForm
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

_REASON = "Paper intake authorization reason long enough for validation in tests."


class MedicalDocumentsNoIntakeApiBranchesTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="ni-doc",
            email="ni.doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.rec = StaffUser.objects.create_user(
            username="ni-rec",
            email="ni.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.rec, "Reception")
        clinic = ClinicSite.objects.create(code="NI", name="No Intake API Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.rec,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="N",
            last_name="Intake",
            date_of_birth=date(1990, 1, 1),
            phone="+48111222333",
            email="ni.patient@example.com",
        )
        self.waiting = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.rec,
        )
        self.admin = StaffUser.objects.create_user(
            username="ni-admin",
            email="ni.admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        authorize_paper_intake(
            queue_entry_id=self.waiting.id,
            authorized_by_user_id=self.admin.id,
            reason=_REASON,
        )
        self.client.force_login(self.doctor)

    def test_get_returns_405(self) -> None:
        r = self.client.get("/api/v1/medical-documents/no-intake")
        self.assertEqual(r.status_code, 405)

    def test_invalid_json_returns_400(self) -> None:
        r = self.client.post(
            "/api/v1/medical-documents/no-intake",
            data="{not-json",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_validation_error_returns_400(self) -> None:
        r = self.client.post(
            "/api/v1/medical-documents/no-intake",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_unknown_queue_entry_returns_404(self) -> None:
        r = self.client.post(
            "/api/v1/medical-documents/no-intake",
            data=json.dumps({"queue_entry_id": str(uuid4())}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)


class QueueEntryPaperIntakeAuthorizationApiBranchesTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.admin = StaffUser.objects.create_user(
            username="qp-admin",
            email="qp.admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.client.force_login(self.admin)

    def test_get_returns_405(self) -> None:
        r = self.client.get(
            f"/api/v1/queue-entries/{uuid4()}/paper-intake-authorization"
        )
        self.assertEqual(r.status_code, 405)

    def test_unknown_queue_entry_returns_404_before_body_parse(self) -> None:
        r = self.client.post(
            f"/api/v1/queue-entries/{uuid4()}/paper-intake-authorization",
            data=json.dumps({"reason": _REASON}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 404)

    def test_invalid_json_returns_400(self) -> None:
        entry = self._make_waiting_entry()
        r = self.client.post(
            f"/api/v1/queue-entries/{entry.id}/paper-intake-authorization",
            data="{",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_validation_error_returns_400(self) -> None:
        entry = self._make_waiting_entry()
        r = self.client.post(
            f"/api/v1/queue-entries/{entry.id}/paper-intake-authorization",
            data=json.dumps({"reason": "short"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def _make_waiting_entry(self) -> QueueEntry:
        rec = StaffUser.objects.create_user(
            username="qp-rec",
            email="qp.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")
        doc = StaffUser.objects.create_user(
            username="qp-doc",
            email="qp.doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(doc, "Doctor")
        clinic = ClinicSite.objects.create(code="QP", name="Queue Paper Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=rec,
            assigned_doctor=doc,
        )
        patient = Patient.objects.create(
            first_name="Q",
            last_name="Paper",
            date_of_birth=date(1991, 2, 2),
            phone="+48222333444",
            email="qp.patient@example.com",
        )
        return QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=rec,
        )


class MedicalDocumentRetryProcessingApiBranchesTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.admin = StaffUser.objects.create_user(
            username="rp-admin",
            email="rp.admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.doc = self._make_document()
        self.client.force_login(self.admin)

    def _make_document(self) -> MedicalDocument:
        rec = StaffUser.objects.create_user(
            username="rp-rec",
            email="rp.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")
        doc_u = StaffUser.objects.create_user(
            username="rp-doc",
            email="rp.doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(doc_u, "Doctor")
        clinic = ClinicSite.objects.create(code="RP", name="Retry Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=rec,
            assigned_doctor=doc_u,
        )
        patient = Patient.objects.create(
            first_name="R",
            last_name="Retry",
            date_of_birth=date(1992, 3, 3),
            phone="+48333444555",
            email="rp.patient@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=rec,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=rec,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )
        md = MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=intake,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            created_by_user=doc_u,
        )
        MedicalDocumentVersion.objects.create(
            medical_document=md,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/tmp/x.pdf",
            publish_request_id=uuid4(),
            published_at=timezone.now(),
            publish_locale="de-DE",
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )
        return md

    def test_invalid_json_returns_400(self) -> None:
        r = self.client.post(
            f"/api/v1/medical-documents/{self.doc.id}/retry-processing",
            data="{",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)


class DoctorTemplatesApiJsonBranchesTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="tpl-json",
            email="tpl.json@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.client.force_login(self.doctor)

    def test_post_invalid_json_returns_400(self) -> None:
        r = self.client.post(
            "/api/v1/doctor-text-templates",
            data="{",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_patch_invalid_json_returns_400(self) -> None:
        r = self.client.patch(
            f"/api/v1/doctor-text-templates/{uuid4()}",
            data="{",
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
