from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import MedicalDocStatus, MedicalDocumentVersion
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
from apps.users.models import StaffRole, StaffUser


class MedicalApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor_user = StaffUser.objects.create_user(
            username="api-doctor",
            email="api.doctor@example.com",
            password="safe-password",
            role=StaffRole.DOCTOR,
            is_staff=True,
        )
        self.reception_user = StaffUser.objects.create_user(
            username="api-reception-medical",
            email="api.reception.medical@example.com",
            password="safe-password",
            role=StaffRole.RECEPTION,
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="API2", name="API Clinic 2")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="B1", name="B1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Medical",
            last_name="Api",
            date_of_birth=date(1988, 8, 8),
            phone="+48111222333",
            email="medical.api@example.com",
            doctolib_patient_id="DOC-API-MED-1",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            token_hash="f" * 64,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        self.queue_entry.active_session = session
        self.queue_entry.save(update_fields=["active_session", "updated_at"])
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature.png",
            signature_sha256="c" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"schema_version": 1, "answers": []},
        )

    def test_medical_document_create_draft_publish_flow(self) -> None:
        create_response = self.client.post(
            "/api/v1/medical-documents",
            data=json.dumps(
                {
                    "queue_entry_id": str(self.queue_entry.id),
                    "intake_form_id": str(self.intake_form.id),
                    "created_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        medical_document_id = create_response.json()["medical_document_id"]

        invalid_draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 2},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(invalid_draft_response.status_code, 400)

        draft_response = self.client.put(
            f"/api/v1/medical-documents/{medical_document_id}/draft",
            data=json.dumps(
                {
                    "updated_by_user_id": str(self.doctor_user.id),
                    "medical_payload_schema_version": 1,
                    "medical_payload": {"schema_version": 1, "authoring_locale": "de-DE", "lesions": []},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_response.json()["version_status"], "DRAFT")

        publish_response = self.client.post(
            f"/api/v1/medical-documents/{medical_document_id}/publish",
            data=json.dumps(
                {
                    "publish_request_id": str(uuid4()),
                    "published_by_user_id": str(self.doctor_user.id),
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["version_status"], "PUBLISHED")

        version_id = publish_response.json()["medical_document_version_id"]
        version = MedicalDocumentVersion.objects.get(id=version_id)
        self.assertEqual(version.version_status, "PUBLISHED")
        self.assertEqual(version.medical_document.status, MedicalDocStatus.PUBLISHED)
