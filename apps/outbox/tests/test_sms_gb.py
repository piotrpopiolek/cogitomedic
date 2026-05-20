"""Outbox SMS_SEND with UK phone numbers (country_code often DE in production)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import phonenumbers
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.services import (
    create_or_get_medical_document,
    publish_document_version,
    save_draft_document_version,
)
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.services import _execute_event
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


class SmsSendGbTests(TestCase):
    @override_settings(SMSAPI_USE_MOCK="1")
    @patch("apps.outbox.services.get_sms_adapter")
    def test_sms_send_uses_inferred_gb_region_not_country_code(
        self, mock_get_adapter: MagicMock
    ) -> None:
        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter

        ex = phonenumbers.example_number("GB")
        self.assertIsNotNone(ex)
        assert ex is not None
        gb_e164 = phonenumbers.format_number(ex, phonenumbers.PhoneNumberFormat.E164)

        doctor = StaffUser.objects.create_user(
            username="doc-sms-gb",
            email="doc-sms-gb@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(doctor, "Doctor")
        reception = StaffUser.objects.create_user(
            username="rec-sms-gb",
            email="rec-sms-gb@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(reception, "Reception")
        clinic = ClinicSite.objects.create(code="GB1", name="GB Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=reception,
        )
        patient = Patient.objects.create(
            first_name="Sms",
            last_name="Gb",
            date_of_birth=date(1991, 4, 4),
            phone=gb_e164,
            email="sms-gb@example.com",
            country_code="DE",
        )
        patient.refresh_from_db()
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=reception,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="en-GB",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=reception,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature-gb-test.png",
            signature_sha256="a" * 64,
            submitted_at=timezone.now(),
        )
        doc = create_or_get_medical_document(
            queue_entry_id=entry.id,
            intake_form_id=intake.id,
            created_by_user_id=doctor.id,
        )
        save_draft_document_version(
            medical_document_id=doc.id,
            updated_by_user_id=doctor.id,
            medical_payload={"authoring_locale": "en-GB"},
        )
        version = publish_document_version(
            medical_document_id=doc.id,
            publish_request_id=uuid4(),
            published_by_user_id=doctor.id,
            publish_locale="en-GB",
        )

        OutboxEvent.objects.filter(medical_document_version=version).delete()
        event = OutboxEvent.objects.create(
            medical_document_version=version,
            event_type=OutboxEventType.SMS_SEND,
            aggregate_id=version.id,
            payload_schema_version=1,
            payload={"medical_document_version_id": str(version.id)},
            status=OutboxStatus.PENDING,
        )

        _execute_event(event, now=timezone.now())

        mock_adapter.send_sms.assert_called_once()
        kwargs = mock_adapter.send_sms.call_args.kwargs
        self.assertEqual(kwargs["default_region"], "GB")
        self.assertEqual(kwargs["to"], patient.phone)
