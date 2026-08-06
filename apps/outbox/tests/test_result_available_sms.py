"""Tests for admin “SMS: result available” without republish."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib import admin, messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import PdfStatus
from apps.medical.services import (
    create_or_get_medical_document,
    publish_document_version,
    save_draft_document_version,
)
from apps.operations.models import AuditEvent
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.result_available_sms import enqueue_result_available_sms_for_patient
from apps.outbox.services import process_outbox_events
from apps.reception.admin import PatientAdmin
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


def _request_with_messages(user: StaffUser):
    factory = RequestFactory()
    request = factory.get("/admin/reception/patient/")
    request.user = user
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


class ResultAvailableSmsServiceTests(TestCase):
    def setUp(self) -> None:
        self.doctor = StaffUser.objects.create_user(
            username="doc-sms-res",
            email="doc-sms-res@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.reception = StaffUser.objects.create_user(
            username="rec-sms-res",
            email="rec-sms-res@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.clinic = ClinicSite.objects.create(code="SMSR", name="SMS Res Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="R1", name="R1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
        )
        self.patient = Patient.objects.create(
            first_name="Anna",
            last_name="Resend",
            date_of_birth=date(1990, 1, 2),
            phone="+491701112233",
            email="anna.resend@example.com",
        )
        self.patient.refresh_from_db()
        self.entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=self.patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception,
        )
        session = PatientFormSession.objects.create(
            queue_entry=self.entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception,
        )
        self.intake = PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature-sms-res.png",
            signature_sha256="b" * 64,
            submitted_at=timezone.now(),
        )

    def _publish_completed_version(self):
        doc = create_or_get_medical_document(
            queue_entry_id=self.entry.id,
            intake_form_id=self.intake.id,
            created_by_user_id=self.doctor.id,
        )
        save_draft_document_version(
            medical_document_id=doc.id,
            updated_by_user_id=self.doctor.id,
            medical_payload={"authoring_locale": "de-DE"},
        )
        version = publish_document_version(
            medical_document_id=doc.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor.id,
            publish_locale="de-DE",
        )
        version.pdf_generation_status = PdfStatus.COMPLETED
        version.pdf_local_path = "medical/test-sms-res.pdf"
        version.save(update_fields=["pdf_generation_status", "pdf_local_path"])
        return version

    def test_enqueue_creates_pending_sms_with_resend_flag(self) -> None:
        version = self._publish_completed_version()
        OutboxEvent.objects.filter(medical_document_version=version).delete()

        event = enqueue_result_available_sms_for_patient(
            patient_id=self.patient.id,
            actor_user_id=self.reception.id,
        )

        self.assertEqual(event.event_type, OutboxEventType.SMS_SEND)
        self.assertEqual(event.status, OutboxStatus.PENDING)
        self.assertIs(event.payload.get("resend_sms"), True)
        audit = AuditEvent.objects.filter(
            event_type="PATIENT_RESULT_AVAILABLE_SMS_ENQUEUED"
        ).latest("event_time")
        self.assertEqual(audit.actor_user_id, self.reception.id)
        self.assertEqual(audit.patient_id, self.patient.id)
        self.assertEqual(
            audit.metadata.get("medical_document_version_id"), str(version.id)
        )
        self.assertIn("phone_e164", audit.metadata)

    def test_enqueue_requeues_processed_sms(self) -> None:
        version = self._publish_completed_version()
        OutboxEvent.objects.filter(medical_document_version=version).delete()
        existing = OutboxEvent.objects.create(
            medical_document_version=version,
            event_type=OutboxEventType.SMS_SEND,
            aggregate_id=version.id,
            payload_schema_version=1,
            payload={"resend_sms": False},
            status=OutboxStatus.PROCESSED,
            processed_at=timezone.now(),
        )

        event = enqueue_result_available_sms_for_patient(
            patient_id=self.patient.id,
            actor_user_id=self.reception.id,
        )

        self.assertEqual(event.id, existing.id)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PENDING)
        self.assertIs(event.payload.get("resend_sms"), True)
        self.assertIsNone(event.processed_at)

    def test_enqueue_requeues_dead_letter(self) -> None:
        version = self._publish_completed_version()
        OutboxEvent.objects.filter(medical_document_version=version).delete()
        OutboxEvent.objects.create(
            medical_document_version=version,
            event_type=OutboxEventType.SMS_SEND,
            aggregate_id=version.id,
            payload_schema_version=1,
            payload={},
            status=OutboxStatus.DEAD_LETTER,
            retry_count=3,
            max_retries=3,
            error_message="boom",
        )

        event = enqueue_result_available_sms_for_patient(
            patient_id=self.patient.id,
            actor_user_id=self.reception.id,
        )
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PENDING)
        self.assertEqual(event.error_message, None)

    def test_no_published_result_raises(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            enqueue_result_available_sms_for_patient(
                patient_id=self.patient.id,
                actor_user_id=self.reception.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.patient_no_published_result_for_sms",
        )

    def test_unsupported_phone_raises(self) -> None:
        self._publish_completed_version()
        # Digits-only US NANP — outside SUPPORTED_SMS_REGIONS (DB stores digits only).
        Patient.objects.filter(pk=self.patient.pk).update(phone="12025550134")
        self.patient.refresh_from_db()

        with self.assertRaises(DomainError) as ctx:
            enqueue_result_available_sms_for_patient(
                patient_id=self.patient.id,
                actor_user_id=self.reception.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.patient_phone_not_supported_for_sms",
        )

    @override_settings(
        SMSAPI_USE_MOCK="1", PATIENT_RESULTS_BASE_URL="https://ergebnisse.test"
    )
    @patch("apps.outbox.services.get_sms_adapter")
    def test_process_outbox_sends_to_current_phone(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter
        version = self._publish_completed_version()
        OutboxEvent.objects.filter(medical_document_version=version).delete()

        self.patient.phone = "+491709998877"
        self.patient.save(update_fields=["phone"])
        self.patient.refresh_from_db()

        enqueue_result_available_sms_for_patient(
            patient_id=self.patient.id,
            actor_user_id=self.reception.id,
        )
        OutboxEvent.objects.filter(
            medical_document_version=version,
            event_type=OutboxEventType.GENERATE_PDF,
        ).delete()
        OutboxEvent.objects.filter(
            medical_document_version=version,
            event_type=OutboxEventType.HIDRIVE_UPLOAD,
        ).delete()

        result = process_outbox_events(batch_size=10)
        self.assertGreaterEqual(result.processed, 1)
        mock_adapter.send_sms.assert_called()
        call_kwargs = mock_adapter.send_sms.call_args.kwargs
        self.assertEqual(call_kwargs["to"], self.patient.phone)
        version.refresh_from_db()
        self.assertTrue(version.sms_sent)


class ResultAvailableSmsAdminTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception = StaffUser.objects.create_user(
            username="rec-admin-sms",
            email="rec-admin-sms@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.doctor = StaffUser.objects.create_user(
            username="doc-admin-sms",
            email="doc-admin-sms@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.superuser = StaffUser.objects.create_superuser(
            username="su-admin-sms",
            email="su-admin-sms@example.com",
            password="safe-password",
        )
        self.clinic = ClinicSite.objects.create(code="ADMS", name="Admin SMS")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="R1", name="R1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
        )
        self.patient = Patient.objects.create(
            first_name="Ben",
            last_name="AdminSms",
            date_of_birth=date(1988, 3, 3),
            phone="+491701234567",
            email="ben.adminsms@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=self.patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception,
        )
        session = PatientFormSession.objects.create(
            queue_entry=self.entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception,
        )
        self.intake = PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature-admin-sms.png",
            signature_sha256="c" * 64,
            submitted_at=timezone.now(),
        )
        self.model_admin = PatientAdmin(Patient, admin.site)

    def _publish_completed(self):
        doc = create_or_get_medical_document(
            queue_entry_id=self.entry.id,
            intake_form_id=self.intake.id,
            created_by_user_id=self.doctor.id,
        )
        save_draft_document_version(
            medical_document_id=doc.id,
            updated_by_user_id=self.doctor.id,
            medical_payload={"authoring_locale": "de-DE"},
        )
        version = publish_document_version(
            medical_document_id=doc.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor.id,
            publish_locale="de-DE",
        )
        version.pdf_generation_status = PdfStatus.COMPLETED
        version.pdf_local_path = "medical/test-admin-sms.pdf"
        version.save(update_fields=["pdf_generation_status", "pdf_local_path"])
        return version

    def test_changelist_action_queues_sms(self) -> None:
        version = self._publish_completed()
        OutboxEvent.objects.filter(medical_document_version=version).delete()
        req = _request_with_messages(self.reception)
        self.model_admin.send_result_available_sms(
            req, Patient.objects.filter(pk=self.patient.pk)
        )
        stored = list(req._messages)
        self.assertTrue(stored)
        self.assertEqual(stored[0].level, messages.SUCCESS)
        event = OutboxEvent.objects.get(
            medical_document_version=version,
            event_type=OutboxEventType.SMS_SEND,
        )
        self.assertEqual(event.status, OutboxStatus.PENDING)
        self.assertIs(event.payload.get("resend_sms"), True)

    def test_changelist_action_no_publish_error(self) -> None:
        req = _request_with_messages(self.reception)
        self.model_admin.send_result_available_sms(
            req, Patient.objects.filter(pk=self.patient.pk)
        )
        stored = list(req._messages)
        self.assertTrue(stored)
        self.assertEqual(stored[0].level, messages.WARNING)
        self.assertIn("Zugangsfenster", stored[0].message)
        self.assertFalse(
            OutboxEvent.objects.filter(event_type=OutboxEventType.SMS_SEND).exists()
        )

    def test_changelist_action_permission_denied_for_doctor(self) -> None:
        self._publish_completed()
        req = _request_with_messages(self.doctor)
        self.model_admin.send_result_available_sms(
            req, Patient.objects.filter(pk=self.patient.pk)
        )
        stored = list(req._messages)
        self.assertTrue(stored)
        self.assertEqual(stored[0].level, messages.ERROR)
        self.assertFalse(
            AuditEvent.objects.filter(
                event_type="PATIENT_RESULT_AVAILABLE_SMS_ENQUEUED",
                actor_user_id=self.doctor.id,
            ).exists()
        )

    def test_change_form_post_queues_sms(self) -> None:
        version = self._publish_completed()
        OutboxEvent.objects.filter(medical_document_version=version).delete()
        self.client.force_login(self.superuser)
        url = reverse(
            "admin:reception_patient_send_result_available_sms",
            args=[self.patient.pk],
        )
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            OutboxEvent.objects.filter(
                medical_document_version=version,
                event_type=OutboxEventType.SMS_SEND,
                status=OutboxStatus.PENDING,
            ).exists()
        )
