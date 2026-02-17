from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from django.test import TestCase
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


class OutboxProcessingTests(TestCase):
    def setUp(self) -> None:
        self.doctor_user = StaffUser.objects.create_user(
            username="doctor-outbox",
            email="doctor.outbox@example.com",
            password="safe-password",
            role=StaffRole.DOCTOR,
            is_staff=True,
        )
        self.reception_user = StaffUser.objects.create_user(
            username="reception-outbox",
            email="reception.outbox@example.com",
            password="safe-password",
            role=StaffRole.RECEPTION,
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="HAM", name="Hamburg")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="H1", name="H1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Outbox",
            last_name="Patient",
            date_of_birth=date(1982, 2, 2),
            phone="+49777777777",
            email="outbox.patient@example.com",
            doctolib_patient_id="DOC-O-1",
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
            token_hash="d" * 64,
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
            signature_sha256="e" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"answers": []},
        )
        self.medical_document = create_or_get_medical_document(
            queue_entry_id=queue_entry.id,
            intake_form_id=intake_form.id,
            created_by_user_id=self.doctor_user.id,
        )
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE"},
        )
        self.version = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
        )

    def test_process_outbox_events_runs_full_chain(self) -> None:
        first = process_outbox_events()
        second = process_outbox_events()
        third = process_outbox_events()

        self.assertEqual(first.processed, 1)
        self.assertEqual(second.processed, 1)
        self.assertEqual(third.processed, 1)

        self.version.refresh_from_db()
        self.assertTrue(self.version.hidrive_sent)
        self.assertTrue(self.version.sms_sent)
        self.assertIsNotNone(self.version.pdf_local_path)

        self.assertEqual(
            OutboxEvent.objects.filter(medical_document_version=self.version, status=OutboxStatus.PROCESSED).count(),
            3,
        )

    def test_process_outbox_events_moves_to_dead_letter_after_retries(self) -> None:
        event = OutboxEvent.objects.get(
            medical_document_version=self.version,
            event_type=OutboxEventType.GENERATE_PDF,
        )
        event.payload = {"simulate_error": True}
        event.max_retries = 1
        event.save(update_fields=["payload", "max_retries", "updated_at"])

        result = process_outbox_events()
        event.refresh_from_db()

        self.assertEqual(result.dead_lettered, 1)
        self.assertEqual(event.status, OutboxStatus.DEAD_LETTER)
