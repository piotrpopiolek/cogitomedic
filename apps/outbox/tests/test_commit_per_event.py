from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.services import (
    create_or_get_medical_document,
    publish_document_version,
    save_draft_document_version,
)
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
from apps.users.models import StaffUser


@override_settings(
    SMSAPI_USE_MOCK="1",
    HIDRIVE_USE_MOCK="1",
    PATIENT_RESULTS_BASE_URL="https://results.example.test",
)
class OutboxCommitPerEventTests(TransactionTestCase):
    def setUp(self) -> None:
        self.doctor_user = StaffUser.objects.create_user(
            username="doctor-cpe",
            email="doctor.cpe@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")

        self.reception_user = StaffUser.objects.create_user(
            username="reception-cpe",
            email="reception.cpe@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        clinic = ClinicSite.objects.create(code="CPE", name="Commit Per Event")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="C1", name="C1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Commit",
            last_name="PerEvent",
            date_of_birth=date(1982, 2, 2),
            phone="+49777777788",
            email="cpe.patient@example.com",
            doctolib_patient_id="DOC-CPE-1",
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
            publish_locale="de-DE",
        )

    @patch("apps.outbox.services.record_outbox_execution")
    @patch("apps.outbox.services.get_sms_adapter")
    def test_sms_commit_survives_crash_after_event_success(
        self, mock_get_sms: MagicMock, mock_record: MagicMock
    ) -> None:
        """After SMS_SEND commits, aborting the batch must not re-send SMS."""
        mock_sms = MagicMock()
        mock_get_sms.return_value = mock_sms

        # Drain GENERATE_PDF + HIDRIVE_UPLOAD first.
        for _ in range(2):
            process_outbox_events(batch_size=1)

        sms_event = OutboxEvent.objects.get(
            medical_document_version=self.version,
            event_type=OutboxEventType.SMS_SEND,
        )
        self.assertEqual(sms_event.status, OutboxStatus.PENDING)

        # Next success metric hook simulates deploy/kill after event TX committed.
        mock_record.side_effect = KeyboardInterrupt("simulated scheduler kill")

        with self.assertRaises(KeyboardInterrupt):
            process_outbox_events(batch_size=10)

        sms_event.refresh_from_db()
        self.version.refresh_from_db()
        self.assertEqual(sms_event.status, OutboxStatus.PROCESSED)
        self.assertTrue(self.version.sms_sent)
        self.assertEqual(mock_sms.send_sms.call_count, 1)

        mock_record.side_effect = None
        mock_record.reset_mock()
        process_outbox_events(batch_size=10)
        self.assertEqual(mock_sms.send_sms.call_count, 1)

    @patch("apps.outbox.services.get_sms_adapter")
    def test_sms_send_skips_provider_when_version_already_sms_sent(
        self, mock_get_sms: MagicMock
    ) -> None:
        mock_sms = MagicMock()
        mock_get_sms.return_value = mock_sms

        for _ in range(3):
            process_outbox_events(batch_size=1)

        self.version.refresh_from_db()
        self.assertTrue(self.version.sms_sent)
        self.assertEqual(mock_sms.send_sms.call_count, 1)

        sms_event = OutboxEvent.objects.get(
            medical_document_version=self.version,
            event_type=OutboxEventType.SMS_SEND,
        )
        sms_event.status = OutboxStatus.PENDING
        sms_event.processed_at = None
        sms_event.available_at = timezone.now()
        sms_event.save(
            update_fields=["status", "processed_at", "available_at", "updated_at"]
        )

        process_outbox_events(batch_size=1)
        self.assertEqual(mock_sms.send_sms.call_count, 1)
        sms_event.refresh_from_db()
        self.assertEqual(sms_event.status, OutboxStatus.PROCESSED)
