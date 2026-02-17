from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.services import create_or_get_medical_document, publish_document_version, save_draft_document_version
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.services import process_outbox_events
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


class OutboxApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor_user = StaffUser.objects.create_user(
            username="api-doctor-outbox",
            email="api.doctor.outbox@example.com",
            password="safe-password",
            role=StaffRole.DOCTOR,
            is_staff=True,
        )
        self.reception_user = StaffUser.objects.create_user(
            username="api-reception-outbox",
            email="api.reception.outbox@example.com",
            password="safe-password",
            role=StaffRole.RECEPTION,
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="API-OUT", name="API Outbox")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="O1", name="O1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Outbox",
            last_name="Api",
            date_of_birth=date(1992, 2, 2),
            phone="+48999111222",
            email="outbox.api@example.com",
            doctolib_patient_id="DOC-OUT-1",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=queue_entry,
            token_hash="b" * 64,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        queue_entry.active_session = session
        queue_entry.save(update_fields=["active_session", "updated_at"])
        intake_form = PatientIntakeForm.objects.create(
            queue_entry=queue_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature.png",
            signature_sha256="a" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"schema_version": 1, "answers": []},
        )
        medical_document = create_or_get_medical_document(
            queue_entry_id=queue_entry.id,
            intake_form_id=intake_form.id,
            created_by_user_id=self.doctor_user.id,
        )
        save_draft_document_version(
            medical_document_id=medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1, "authoring_locale": "de-DE"},
        )
        self.published_version = publish_document_version(
            medical_document_id=medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
        )

    def test_outbox_events_list_endpoint(self) -> None:
        response = self.client.get("/api/v1/outbox-events?status=PENDING&limit=10")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["status"], "PENDING")

    def test_operations_outbox_process_endpoint(self) -> None:
        response = self.client.post(
            "/api/v1/operations/outbox/process",
            data=json.dumps({"limit": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["processed"], 1)

    def test_outbox_event_retry_endpoint(self) -> None:
        event = OutboxEvent.objects.get(
            medical_document_version=self.published_version,
            event_type=OutboxEventType.GENERATE_PDF,
        )
        event.payload = {"simulate_error": True}
        event.max_retries = 1
        event.save(update_fields=["payload", "max_retries", "updated_at"])
        process_outbox_events(batch_size=10)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.DEAD_LETTER)

        response = self.client.post(
            f"/api/v1/outbox-events/{event.id}/retry",
            data=json.dumps({"reason": "manual retry"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PENDING)
