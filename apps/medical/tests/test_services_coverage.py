"""Tests covering uncovered lines in apps.medical.services."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from freezegun import freeze_time

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.medical.services import (
    create_or_get_medical_document,
    get_medical_document_context,
    latest_retryable_outbox_event,
    latest_version_processing_error_message,
    list_doctor_work_queue,
    outbox_event_stage_status,
    revoke_document_version,
    save_draft_document_version,
)
from apps.outbox.models import (
    OutboxEvent,
    OutboxEventType,
    OutboxStatus,
)
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


class ServicesCoverageBase(TestCase):
    """Shared fixtures for medical-services coverage tests."""

    @classmethod
    def setUpTestData(cls):
        cls.doctor = StaffUser.objects.create_user(
            username="cov-doctor",
            email="cov-doctor@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(cls.doctor, "Doctor")

        cls.clinic = ClinicSite.objects.create(code="COV", name="Coverage Clinic")
        cls.room = ConsultingRoom.objects.create(
            clinic_site=cls.clinic, code="C1", name="C1"
        )
        cls.daily_queue = DailyQueue.objects.create(
            queue_date=date(2026, 3, 10),
            clinic_site=cls.clinic,
            consulting_room=cls.room,
            status=QueueStatus.OPEN,
            assigned_doctor=cls.doctor,
            created_by_user=cls.doctor,
        )
        cls.patient = Patient.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            date_of_birth=date(1985, 5, 15),
            phone="48500111222",
            email="anna@example.com",
        )
        cls.queue_entry = QueueEntry.objects.create(
            daily_queue=cls.daily_queue,
            patient=cls.patient,
            entry_status=QueueEntryStatus.PUBLISHED,
            position_no=1,
            created_by_user=cls.doctor,
        )
        cls.session = PatientFormSession.objects.create(
            queue_entry=cls.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=cls.doctor,
        )
        cls.intake = PatientIntakeForm.objects.create(
            queue_entry=cls.queue_entry,
            session=cls.session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )

    def _make_medical_doc(self, **overrides):
        defaults = dict(
            queue_entry=self.queue_entry,
            intake_form=self.intake,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            created_by_user=self.doctor,
        )
        defaults.update(overrides)
        return MedicalDocument.objects.create(**defaults)

    def _make_published_version(self, doc, *, version_no=1, **kw):
        defaults = dict(
            medical_document=doc,
            version_no=version_no,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/media/befund/test.pdf",
            publish_request_id=uuid.uuid4(),
            published_at=timezone.now(),
            publish_locale="de-DE",
        )
        defaults.update(kw)
        return MedicalDocumentVersion.objects.create(**defaults)


# ------------------------------------------------------------------
# 1. create_or_get_medical_document validation errors (lines 132, 137)
# ------------------------------------------------------------------
class CreateOrGetMedicalDocumentValidationTests(ServicesCoverageBase):
    def test_intake_form_wrong_queue_entry_raises(self):
        other_qe = QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=self.patient,
            entry_status=QueueEntryStatus.PUBLISHED,
            position_no=2,
            created_by_user=self.doctor,
        )
        with self.assertRaises(DomainError) as ctx:
            create_or_get_medical_document(
                queue_entry_id=other_qe.id,
                intake_form_id=self.intake.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertIn(
            "intake_form_wrong_queue_entry",
            ctx.exception.api_message_key,
        )

    def test_intake_form_not_submitted_raises(self):
        other_patient = Patient.objects.create(
            first_name="Jan",
            last_name="Nowak",
            date_of_birth=date(1990, 2, 2),
            phone="48600222333",
            email="jan@example.com",
        )
        other_qe = QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.PUBLISHED,
            position_no=3,
            created_by_user=self.doctor,
        )
        other_session = PatientFormSession.objects.create(
            queue_entry=other_qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        in_progress_intake = PatientIntakeForm.objects.create(
            queue_entry=other_qe,
            session=other_session,
            form_status=IntakeStatus.IN_PROGRESS,
        )
        with self.assertRaises(DomainError) as ctx:
            create_or_get_medical_document(
                queue_entry_id=other_qe.id,
                intake_form_id=in_progress_intake.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertIn(
            "intake_form_must_be_submitted",
            ctx.exception.api_message_key,
        )


# ------------------------------------------------------------------
# 2. save_draft_document_version — republish after retention
#    (lines 197-198)
# ------------------------------------------------------------------
class SaveDraftRepublishAfterRetentionTests(ServicesCoverageBase):
    @freeze_time("2026-03-10T12:00:00Z")
    def test_republish_after_retention_raises(self):
        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
            local_pdf_deleted_at=timezone.now(),
        )
        with self.assertRaises(DomainError) as ctx:
            save_draft_document_version(
                medical_document_id=doc.id,
                updated_by_user_id=self.doctor.id,
                medical_payload={"authoring_locale": "de-DE"},
            )
        self.assertIn(
            "republish_after_retention_not_allowed",
            ctx.exception.api_message_key,
        )


# ------------------------------------------------------------------
# 3. revoke_document_version (lines 442-499) — whole function
# ------------------------------------------------------------------
class RevokeDocumentVersionTests(ServicesCoverageBase):
    @freeze_time("2026-03-10T12:00:00Z")
    @patch("apps.medical.services._try_delete_file")
    def test_happy_path_revokes_published_version(self, mock_del):
        doc = self._make_medical_doc()
        ver = self._make_published_version(
            doc,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )

        result = revoke_document_version(
            medical_document_id=doc.id,
            revoked_by_user_id=self.doctor.id,
        )

        result.refresh_from_db()
        self.assertIsNotNone(result.revoked_at)
        self.assertIsNone(result.pdf_local_path)
        mock_del.assert_called_once_with("/media/befund/test.pdf")
        self.assertEqual(result.id, ver.id)

    def test_no_published_version_raises(self):
        doc = self._make_medical_doc(
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
        )
        with self.assertRaises(DomainError) as ctx:
            revoke_document_version(
                medical_document_id=doc.id,
                revoked_by_user_id=self.doctor.id,
            )
        self.assertIn(
            "no_published_version_to_revoke",
            ctx.exception.api_message_key,
        )

    @freeze_time("2026-03-10T12:00:00Z")
    @patch("apps.medical.services._try_delete_file")
    def test_already_revoked_is_idempotent(self, mock_del):
        doc = self._make_medical_doc()
        ver = self._make_published_version(doc, revoked_at=timezone.now())

        result = revoke_document_version(
            medical_document_id=doc.id,
            revoked_by_user_id=self.doctor.id,
        )

        self.assertEqual(result.id, ver.id)
        mock_del.assert_not_called()

    @freeze_time("2026-03-10T12:00:00Z")
    @patch("apps.medical.services._try_delete_file")
    def test_sets_local_pdf_deleted_at_when_fully_sent(self, mock_del):
        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )

        result = revoke_document_version(
            medical_document_id=doc.id,
            revoked_by_user_id=self.doctor.id,
        )

        result.refresh_from_db()
        self.assertIsNotNone(result.local_pdf_deleted_at)

    @freeze_time("2026-03-10T12:00:00Z")
    @patch("apps.medical.services._try_delete_file")
    def test_revoke_creates_audit_event(self, mock_del):
        from apps.operations.models import AuditEvent

        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )

        revoke_document_version(
            medical_document_id=doc.id,
            revoked_by_user_id=self.doctor.id,
        )

        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="DOCUMENT_REVOKED",
            ).exists()
        )


# ------------------------------------------------------------------
# 4. list_doctor_work_queue (lines 600-705) — whole function
# ------------------------------------------------------------------
class ListDoctorWorkQueueTests(ServicesCoverageBase):
    def test_returns_intake_for_assigned_doctor(self):
        doc = self._make_medical_doc()
        self._make_published_version(doc)

        items, total = list_doctor_work_queue(user=self.doctor)

        self.assertEqual(total, 1)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["queue_entry_id"], str(self.queue_entry.id))
        self.assertEqual(item["patient"]["last_name"], "Kowalska")
        self.assertEqual(item["document_id"], str(doc.id))

    def test_empty_when_no_submitted_intake(self):
        self.intake.form_status = IntakeStatus.IN_PROGRESS
        self.intake.submitted_at = None
        self.intake.signature_sha256 = None
        self.intake.save(
            update_fields=[
                "form_status",
                "submitted_at",
                "signature_sha256",
            ]
        )
        items, total = list_doctor_work_queue(user=self.doctor)
        self.assertEqual(total, 0)
        self.assertEqual(items, [])
        # restore
        self.intake.form_status = IntakeStatus.SUBMITTED
        self.intake.submitted_at = timezone.now()
        self.intake.signature_sha256 = "a" * 64
        self.intake.save(
            update_fields=[
                "form_status",
                "submitted_at",
                "signature_sha256",
            ]
        )

    def test_entry_without_medical_doc(self):
        items, total = list_doctor_work_queue(user=self.doctor)
        self.assertEqual(total, 1)
        item = items[0]
        self.assertIsNone(item["document_id"])
        self.assertEqual(item["status"], "—")

    def test_queue_date_filter(self):
        items, total = list_doctor_work_queue(
            user=self.doctor,
            queue_date=date(2026, 3, 10),
        )
        self.assertEqual(total, 1)

        items, total = list_doctor_work_queue(
            user=self.doctor,
            queue_date=date(2000, 1, 1),
        )
        self.assertEqual(total, 0)

    def test_patient_search_filter(self):
        items, total = list_doctor_work_queue(
            user=self.doctor, patient_search="Kowalska"
        )
        self.assertEqual(total, 1)

        items, total = list_doctor_work_queue(
            user=self.doctor, patient_search="Nonexistent"
        )
        self.assertEqual(total, 0)

    def test_non_assigned_doctor_sees_nothing(self):
        other = StaffUser.objects.create_user(
            username="other-doc",
            email="other-doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        items, total = list_doctor_work_queue(user=other)
        self.assertEqual(total, 0)


# ------------------------------------------------------------------
# 5. get_medical_document_context — retention branch (lines 772-809)
# ------------------------------------------------------------------
class GetMedicalDocumentContextRetentionTests(ServicesCoverageBase):
    @freeze_time("2026-03-10T12:00:00Z")
    @patch("apps.medical.services.get_intake_form_context")
    def test_retention_expired_branch(self, mock_ctx):
        mock_ctx.return_value = {
            "consents": [],
            "body_map_data": [],
            "anamnesis_questions": [],
            "patient": None,
        }
        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
            local_pdf_deleted_at=timezone.now(),
        )

        result = get_medical_document_context(
            medical_document_id=doc.id, user=self.doctor
        )

        cv = result["current_version"]
        self.assertTrue(cv["retention_expired"])
        self.assertIn("local_pdf_deleted_at", cv)
        self.assertNotIn("medical_payload", cv)


# ------------------------------------------------------------------
# 6a. outbox_event_stage_status (lines 50-58)
# ------------------------------------------------------------------
class OutboxEventStageStatusTests(TestCase):
    def test_completed_true_returns_completed(self):
        self.assertEqual(
            outbox_event_stage_status(None, completed=True),
            "COMPLETED",
        )

    def test_event_none_pending(self):
        self.assertEqual(
            outbox_event_stage_status(None, completed=False),
            "PENDING",
        )

    def test_event_processed_returns_completed(self):
        event = Mock(status=OutboxStatus.PROCESSED)
        self.assertEqual(
            outbox_event_stage_status(event, completed=False),
            "COMPLETED",
        )

    def test_event_failed_returns_failed(self):
        event = Mock(status=OutboxStatus.FAILED)
        self.assertEqual(
            outbox_event_stage_status(event, completed=False),
            "FAILED",
        )

    def test_event_pending_returns_pending(self):
        event = Mock(status=OutboxStatus.PENDING)
        self.assertEqual(
            outbox_event_stage_status(event, completed=False),
            OutboxStatus.PENDING,
        )

    def test_event_processing_returns_processing(self):
        event = Mock(status=OutboxStatus.PROCESSING)
        self.assertEqual(
            outbox_event_stage_status(event, completed=False),
            OutboxStatus.PROCESSING,
        )


# ------------------------------------------------------------------
# 6b. latest_retryable_outbox_event (lines 70, 79)
# ------------------------------------------------------------------
class LatestRetryableOutboxEventTests(ServicesCoverageBase):
    @freeze_time("2026-03-10T12:00:00Z")
    def test_returns_none_when_pending_in_flight(self):
        doc = self._make_medical_doc()
        ver = self._make_published_version(doc)
        OutboxEvent.objects.create(
            medical_document_version=ver,
            aggregate_id=ver.id,
            event_type=OutboxEventType.GENERATE_PDF,
            status=OutboxStatus.PENDING,
            payload={},
            payload_schema_version=1,
        )
        result = latest_retryable_outbox_event(ver)
        self.assertIsNone(result)

    @freeze_time("2026-03-10T12:00:00Z")
    def test_returns_none_when_no_failed_events(self):
        doc = self._make_medical_doc()
        ver = self._make_published_version(doc)
        OutboxEvent.objects.create(
            medical_document_version=ver,
            aggregate_id=ver.id,
            event_type=OutboxEventType.GENERATE_PDF,
            status=OutboxStatus.PROCESSED,
            payload={},
            payload_schema_version=1,
        )
        result = latest_retryable_outbox_event(ver)
        self.assertIsNone(result)

    @freeze_time("2026-03-10T12:00:00Z")
    def test_returns_failed_event(self):
        doc = self._make_medical_doc()
        ver = self._make_published_version(doc)
        evt = OutboxEvent.objects.create(
            medical_document_version=ver,
            aggregate_id=ver.id,
            event_type=OutboxEventType.GENERATE_PDF,
            status=OutboxStatus.FAILED,
            payload={},
            payload_schema_version=1,
        )
        result = latest_retryable_outbox_event(ver)
        self.assertEqual(result.id, evt.id)

    @freeze_time("2026-03-10T12:00:00Z")
    def test_returns_dead_letter_event(self):
        doc = self._make_medical_doc()
        ver = self._make_published_version(doc)
        evt = OutboxEvent.objects.create(
            medical_document_version=ver,
            aggregate_id=ver.id,
            event_type=OutboxEventType.SMS_SEND,
            status=OutboxStatus.DEAD_LETTER,
            payload={},
            payload_schema_version=1,
        )
        result = latest_retryable_outbox_event(ver)
        self.assertEqual(result.id, evt.id)


# ------------------------------------------------------------------
# 6c. latest_version_processing_error_message (lines 85-95)
# ------------------------------------------------------------------
class LatestVersionProcessingErrorTests(ServicesCoverageBase):
    @freeze_time("2026-03-10T12:00:00Z")
    def test_returns_none_when_no_failed(self):
        doc = self._make_medical_doc()
        ver = self._make_published_version(doc)
        OutboxEvent.objects.create(
            medical_document_version=ver,
            aggregate_id=ver.id,
            event_type=OutboxEventType.GENERATE_PDF,
            status=OutboxStatus.PROCESSED,
            payload={},
            payload_schema_version=1,
        )
        self.assertIsNone(latest_version_processing_error_message(ver))

    @freeze_time("2026-03-10T12:00:00Z")
    def test_returns_error_message_from_failed(self):
        doc = self._make_medical_doc()
        ver = self._make_published_version(doc)
        OutboxEvent.objects.create(
            medical_document_version=ver,
            aggregate_id=ver.id,
            event_type=OutboxEventType.GENERATE_PDF,
            status=OutboxStatus.FAILED,
            error_message="PDF generation timed out",
            payload={},
            payload_schema_version=1,
        )
        msg = latest_version_processing_error_message(ver)
        self.assertEqual(msg, "PDF generation timed out")

    @freeze_time("2026-03-10T12:00:00Z")
    def test_ignores_blank_error_message(self):
        doc = self._make_medical_doc()
        ver = self._make_published_version(doc)
        OutboxEvent.objects.create(
            medical_document_version=ver,
            aggregate_id=ver.id,
            event_type=OutboxEventType.GENERATE_PDF,
            status=OutboxStatus.FAILED,
            error_message="  ",
            payload={},
            payload_schema_version=1,
        )
        self.assertIsNone(latest_version_processing_error_message(ver))
