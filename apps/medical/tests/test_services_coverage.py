"""Tests covering uncovered lines in apps.medical.services."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone as dt_timezone
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from freezegun import freeze_time

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.constants import DOCUMENT_LOCK_TIMEOUT_HOURS
from apps.medical.external_pdf_service import (
    hidrive_incoming_dir,
    hidrive_processed_dir,
)
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
    PaperIntakeAuthorization,
    PdfStatus,
)
from apps.medical.services import (
    acquire_document_lock,
    create_external_upload_medical_document,
    create_or_get_medical_document,
    select_external_upload_attachment_for_draft,
    get_document_lock_state,
    get_medical_document_context,
    latest_retryable_outbox_event,
    latest_version_processing_error_message,
    list_doctor_work_queue,
    list_medical_documents,
    outbox_event_stage_status,
    pdf_generation_stage_complete,
    refresh_document_lock,
    release_document_lock,
    revoke_document_version,
    save_draft_document_version,
    work_queue_row_outbound_complete,
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
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
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

    def _make_queue_entry(self, **overrides):
        defaults = dict(
            daily_queue=self.daily_queue,
            patient=self.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=99,
            created_by_user=self.doctor,
        )
        defaults.update(overrides)
        return QueueEntry.objects.create(**defaults)

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
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
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
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
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

    def test_intake_form_reopened_raises_on_create_medical_document(self):
        other_patient = Patient.objects.create(
            first_name="Ewa",
            last_name="Kowal",
            date_of_birth=date(1991, 3, 3),
            phone="48600333444",
            email="ewa@example.com",
        )
        other_qe = QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=4,
            created_by_user=self.doctor,
        )
        other_session = PatientFormSession.objects.create(
            queue_entry=other_qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        reopened_intake = PatientIntakeForm.objects.create(
            queue_entry=other_qe,
            session=other_session,
            form_status=IntakeStatus.REOPENED,
        )
        with self.assertRaises(DomainError) as ctx:
            create_or_get_medical_document(
                queue_entry_id=other_qe.id,
                intake_form_id=reopened_intake.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertIn(
            "intake_form_must_be_submitted",
            ctx.exception.api_message_key,
        )


class CreateExternalUploadMedicalDocumentTests(ServicesCoverageBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.reception = StaffUser.objects.create_user(
            username="cov-reception-eu",
            email="cov-reception-eu@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(cls.reception, "Reception")

    def test_submitted_creates_document_and_draft_v1(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        self.assertEqual(doc.source_type, MedicalDocumentSourceType.EXTERNAL_UPLOAD)
        self.assertEqual(doc.status, MedicalDocStatus.DRAFT)
        self.assertEqual(doc.current_version_no, 1)
        v = MedicalDocumentVersion.objects.get(medical_document=doc, version_no=1)
        self.assertEqual(v.version_status, DocVersionStatus.DRAFT)
        self.assertEqual(v.medical_payload, {})
        self.assertEqual(v.pdf_generation_status, PdfStatus.PENDING)

    def test_second_call_is_idempotent(self) -> None:
        a = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        b = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        self.assertEqual(a.id, b.id)
        self.assertEqual(
            MedicalDocumentVersion.objects.filter(medical_document_id=a.id).count(),
            1,
        )

    def test_reopened_intake_allowed(self) -> None:
        qe = self._make_queue_entry(position_no=50)
        session = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=session,
            form_status=IntakeStatus.REOPENED,
        )
        doc = create_external_upload_medical_document(
            queue_entry_id=qe.id,
            created_by_user_id=self.reception.id,
        )
        self.assertEqual(doc.source_type, MedicalDocumentSourceType.EXTERNAL_UPLOAD)

    def test_in_progress_raises(self) -> None:
        qe = self._make_queue_entry(position_no=51)
        session = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
        )
        with self.assertRaises(DomainError) as ctx:
            create_external_upload_medical_document(
                queue_entry_id=qe.id,
                created_by_user_id=self.reception.id,
            )
        self.assertIn(
            "external_upload_intake_not_ready",
            ctx.exception.api_message_key,
        )

    def test_no_intake_form_raises(self) -> None:
        qe = self._make_queue_entry(position_no=52)
        with self.assertRaises(DomainError) as ctx:
            create_external_upload_medical_document(
                queue_entry_id=qe.id,
                created_by_user_id=self.reception.id,
            )
        self.assertIn(
            "queue_entry_or_intake_not_found",
            ctx.exception.api_message_key,
        )

    def test_unknown_queue_entry_raises(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_external_upload_medical_document(
                queue_entry_id=uuid.uuid4(),
                created_by_user_id=self.reception.id,
            )
        self.assertIn("queue_entry_not_found", ctx.exception.api_message_key)

    def test_mismatch_when_digital_document_exists(self) -> None:
        self._make_medical_doc(
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
        )
        with self.assertRaises(DomainError) as ctx:
            create_external_upload_medical_document(
                queue_entry_id=self.queue_entry.id,
                created_by_user_id=self.reception.id,
            )
        self.assertIn(
            "medical_document_source_type_mismatch",
            ctx.exception.api_message_key,
        )

    def test_doctor_role_raises(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_external_upload_medical_document(
                queue_entry_id=self.queue_entry.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertIn(
            "external_upload_create_document_invalid_role",
            ctx.exception.api_message_key,
        )

    def test_unknown_actor_user_raises(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_external_upload_medical_document(
                queue_entry_id=self.queue_entry.id,
                created_by_user_id=uuid.uuid4(),
            )
        self.assertIn("staff_user_not_found", ctx.exception.api_message_key)


class SelectExternalUploadAttachmentForDraftTests(
    CreateExternalUploadMedicalDocumentTests
):
    def _incoming_external_path(self, filename: str = "x.pdf") -> str:
        return (
            f"{hidrive_incoming_dir()}/external-upload/{self.queue_entry.id}/{filename}"
        )

    def _processed_external_path(
        self, queue_entry_id, filename: str = "old.pdf"
    ) -> str:
        return f"{hidrive_processed_dir()}/external-upload/{queue_entry_id}/{filename}"

    def test_select_matched_sets_audit_and_clears_prior_pdf_fields(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        draft = MedicalDocumentVersion.objects.get(medical_document=doc, version_no=1)
        draft.pdf_local_path = "pdfs/stale.pdf"
        draft.pdf_checksum_sha256 = "a" * 64
        draft.pdf_generation_status = PdfStatus.COMPLETED
        draft.save(
            update_fields=[
                "pdf_local_path",
                "pdf_checksum_sha256",
                "pdf_generation_status",
            ]
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=doc,
            hidrive_remote_path=self._incoming_external_path(),
            original_filename="x.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        out = select_external_upload_attachment_for_draft(
            medical_document_id=doc.id,
            attachment_id=att.id,
            actor_user_id=self.reception.id,
        )
        self.assertEqual(out.id, draft.id)
        out.refresh_from_db()
        self.assertEqual(out.external_selected_attachment_id, att.id)
        self.assertEqual(out.external_original_filename, "x.pdf")
        self.assertEqual(out.external_uploaded_by_user_id, self.reception.id)
        self.assertIsNotNone(out.external_uploaded_at)
        self.assertIsNone(out.pdf_local_path)
        self.assertIsNone(out.pdf_checksum_sha256)
        self.assertEqual(out.pdf_generation_status, PdfStatus.PENDING)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.MATCHED)

    def test_select_accepted_processed_path(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        path = self._processed_external_path(self.queue_entry.id)
        att = ExternalPdfAttachment.objects.create(
            medical_document=doc,
            hidrive_remote_path=path,
            original_filename="old.pdf",
            status=ExternalPdfStatus.ACCEPTED,
        )
        select_external_upload_attachment_for_draft(
            medical_document_id=doc.id,
            attachment_id=att.id,
            actor_user_id=self.reception.id,
        )
        draft = MedicalDocumentVersion.objects.get(medical_document=doc, version_no=1)
        self.assertEqual(draft.external_selected_attachment_id, att.id)

    def test_rejected_status_raises(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=doc,
            hidrive_remote_path=self._incoming_external_path(),
            original_filename="bad.pdf",
            status=ExternalPdfStatus.REJECTED,
        )
        with self.assertRaises(DomainError) as ctx:
            select_external_upload_attachment_for_draft(
                medical_document_id=doc.id,
                attachment_id=att.id,
                actor_user_id=self.reception.id,
            )
        self.assertIn(
            "external_upload_attachment_invalid_status",
            ctx.exception.api_message_key,
        )

    def test_attachment_wrong_document_raises(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        other_qe = self._make_queue_entry(position_no=77)
        other_session = PatientFormSession.objects.create(
            queue_entry=other_qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        PatientIntakeForm.objects.create(
            queue_entry=other_qe,
            session=other_session,
            form_status=IntakeStatus.SUBMITTED,
            signature_sha256="b" * 64,
            submitted_at=timezone.now(),
        )
        other_doc = create_external_upload_medical_document(
            queue_entry_id=other_qe.id,
            created_by_user_id=self.reception.id,
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=other_doc,
            hidrive_remote_path=f"{hidrive_incoming_dir()}/external-upload/{other_qe.id}/o.pdf",
            original_filename="o.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.assertRaises(DomainError) as ctx:
            select_external_upload_attachment_for_draft(
                medical_document_id=doc.id,
                attachment_id=att.id,
                actor_user_id=self.reception.id,
            )
        self.assertIn(
            "external_upload_attachment_not_found",
            ctx.exception.api_message_key,
        )

    def test_non_external_document_raises(self) -> None:
        digital_doc = self._make_medical_doc(
            status=MedicalDocStatus.DRAFT,
            current_version_no=1,
        )
        MedicalDocumentVersion.objects.create(
            medical_document=digital_doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            medical_payload_schema_version=1,
            medical_payload={},
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=digital_doc,
            hidrive_remote_path=f"{hidrive_incoming_dir()}/external-upload/{self.queue_entry.id}/d.pdf",
            original_filename="d.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.assertRaises(DomainError) as ctx:
            select_external_upload_attachment_for_draft(
                medical_document_id=digital_doc.id,
                attachment_id=att.id,
                actor_user_id=self.reception.id,
            )
        self.assertIn(
            "external_upload_not_external_source",
            ctx.exception.api_message_key,
        )

    def test_no_active_draft_raises(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        draft = MedicalDocumentVersion.objects.get(medical_document=doc, version_no=1)
        rid = uuid.uuid4()
        now = timezone.now()
        draft.version_status = DocVersionStatus.PUBLISHED
        draft.publish_request_id = rid
        draft.published_at = now
        draft.publish_locale = "de-DE"
        draft.save(
            update_fields=[
                "version_status",
                "publish_request_id",
                "published_at",
                "publish_locale",
            ]
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=doc,
            hidrive_remote_path=self._incoming_external_path(),
            original_filename="x.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.assertRaises(DomainError) as ctx:
            select_external_upload_attachment_for_draft(
                medical_document_id=doc.id,
                attachment_id=att.id,
                actor_user_id=self.reception.id,
            )
        self.assertIn(
            "external_upload_no_active_draft",
            ctx.exception.api_message_key,
        )

    def test_invalid_hidrive_prefix_raises(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=doc,
            hidrive_remote_path=f"{hidrive_incoming_dir()}/lab-result.pdf",
            original_filename="lab-result.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.assertRaises(DomainError) as ctx:
            select_external_upload_attachment_for_draft(
                medical_document_id=doc.id,
                attachment_id=att.id,
                actor_user_id=self.reception.id,
            )
        self.assertIn(
            "external_upload_attachment_path_invalid",
            ctx.exception.api_message_key,
        )

    def test_doctor_role_raises(self) -> None:
        doc = create_external_upload_medical_document(
            queue_entry_id=self.queue_entry.id,
            created_by_user_id=self.reception.id,
        )
        att = ExternalPdfAttachment.objects.create(
            medical_document=doc,
            hidrive_remote_path=self._incoming_external_path(),
            original_filename="x.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        with self.assertRaises(DomainError) as ctx:
            select_external_upload_attachment_for_draft(
                medical_document_id=doc.id,
                attachment_id=att.id,
                actor_user_id=self.doctor.id,
            )
        self.assertIn(
            "external_upload_select_attachment_invalid_role",
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
                intent="amend",
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
    def test_not_fully_sent_raises(self):
        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=False,
        )
        with self.assertRaises(DomainError) as ctx:
            revoke_document_version(
                medical_document_id=doc.id,
                revoked_by_user_id=self.doctor.id,
            )
        self.assertIn(
            "revoke_requires_full_delivery",
            ctx.exception.api_message_key,
        )

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

    def test_draft_sorts_before_published_even_when_published_is_newer(self):
        """DRAFT/unpublished rows must precede PUBLISHED regardless of doctor_list_sort_at."""
        admin = StaffUser.objects.create_user(
            username="admin-sort-test",
            email="admin-sort-test@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(admin, "Admin")

        now = timezone.now()
        patient_pub = Patient.objects.create(
            first_name="X",
            last_name="Y",
            date_of_birth=date(1990, 1, 1),
            phone="48500111223",
            email="xy@example.com",
        )
        q_pub = QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=patient_pub,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=50,
            created_by_user=self.doctor,
            doctor_list_sort_at=now,
        )
        sess_pub = PatientFormSession.objects.create(
            queue_entry=q_pub,
            form_locale="de-DE",
            expires_at=now + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        intake_pub = PatientIntakeForm.objects.create(
            queue_entry=q_pub,
            session=sess_pub,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=now,
            signature_sha256="b" * 64,
        )
        doc_pub = MedicalDocument.objects.create(
            queue_entry=q_pub,
            intake_form=intake_pub,
            source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            created_by_user=self.doctor,
        )
        self._make_published_version(doc_pub, version_no=1)

        self.queue_entry.doctor_list_sort_at = now - timedelta(hours=1)
        self.queue_entry.save(update_fields=["doctor_list_sort_at"])
        doc_draft = self._make_medical_doc(status=MedicalDocStatus.DRAFT)
        self._make_published_version(
            doc_draft,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            publish_request_id=None,
            published_at=None,
            publish_locale=None,
        )

        items, total = list_doctor_work_queue(user=admin, page=1, page_size=20)
        self.assertEqual(total, 2)
        self.assertEqual(items[0]["status"], "DRAFT")
        self.assertEqual(items[0]["patient"]["last_name"], "Kowalska")
        self.assertEqual(items[1]["status"], "PUBLISHED")
        self.assertEqual(items[1]["patient"]["last_name"], "Y")

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
        self.assertFalse(item["paper_intake_action_required"])

    def test_paper_authorized_without_document_is_listed_with_action_flag(self):
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
        paper_entry = self._make_queue_entry(position_no=2)
        PaperIntakeAuthorization.objects.create(
            queue_entry=paper_entry,
            authorized_at=timezone.now(),
            authorized_by=self.doctor,
            reason="Papier od pacjenta",
        )

        items, total = list_doctor_work_queue(user=self.doctor)

        self.assertEqual(total, 1)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["queue_entry_id"], str(paper_entry.id))
        self.assertTrue(item["paper_intake_action_required"])
        self.assertIsNone(item["document_id"])
        self.assertIsNone(item["intake_form_id"])
        self.assertEqual(item["row_unpublished_urgency"], 1.0)
        self.assertIsNone(item["row_unpublished_sla_deadline_at"])

    @freeze_time("2026-03-10T14:00:00Z")
    def test_unpublished_sla_urgency_half_after_12h_rolling(self):
        t0 = datetime(2026, 3, 10, 2, 0, 0, tzinfo=dt_timezone.utc)
        self.queue_entry.doctor_list_sort_at = t0
        self.queue_entry.save(update_fields=["doctor_list_sort_at"])
        doc_d = self._make_medical_doc(status=MedicalDocStatus.DRAFT)
        self._make_published_version(
            doc_d,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            publish_request_id=None,
            published_at=None,
            publish_locale=None,
        )
        items, total = list_doctor_work_queue(user=self.doctor)
        row = next(i for i in items if i["queue_entry_id"] == str(self.queue_entry.id))
        self.assertAlmostEqual(row["row_unpublished_urgency"], 0.5, places=4)
        self.assertIsNotNone(row["row_unpublished_sla_deadline_at"])

    @freeze_time("2026-03-10T12:00:00Z")
    def test_unpublished_sla_urgency_zero_immediately_at_t0(self):
        t0 = datetime(2026, 3, 10, 12, 0, 0, tzinfo=dt_timezone.utc)
        self.queue_entry.doctor_list_sort_at = t0
        self.queue_entry.save(update_fields=["doctor_list_sort_at"])
        doc_d = self._make_medical_doc(status=MedicalDocStatus.DRAFT)
        self._make_published_version(
            doc_d,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            publish_request_id=None,
            published_at=None,
            publish_locale=None,
        )
        items, total = list_doctor_work_queue(user=self.doctor)
        row = next(i for i in items if i["queue_entry_id"] == str(self.queue_entry.id))
        self.assertEqual(row["row_unpublished_urgency"], 0.0)

    @freeze_time("2026-03-11T13:00:00Z")
    def test_unpublished_sla_urgency_one_after_25h(self):
        t0 = datetime(2026, 3, 10, 12, 0, 0, tzinfo=dt_timezone.utc)
        self.queue_entry.doctor_list_sort_at = t0
        self.queue_entry.save(update_fields=["doctor_list_sort_at"])
        doc_d = self._make_medical_doc(status=MedicalDocStatus.DRAFT)
        self._make_published_version(
            doc_d,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            publish_request_id=None,
            published_at=None,
            publish_locale=None,
        )
        items, total = list_doctor_work_queue(user=self.doctor)
        row = next(i for i in items if i["queue_entry_id"] == str(self.queue_entry.id))
        self.assertEqual(row["row_unpublished_urgency"], 1.0)

    def test_paper_intake_completed_with_document_is_listed(self):
        paper_entry = self._make_queue_entry(
            position_no=3,
            entry_status=QueueEntryStatus.PAPER_INTAKE_COMPLETED,
        )
        paper_doc = self._make_medical_doc(
            queue_entry=paper_entry,
            intake_form=None,
            source_type=MedicalDocumentSourceType.PAPER_INTAKE,
            status=MedicalDocStatus.DRAFT,
        )

        items, total = list_doctor_work_queue(user=self.doctor)

        self.assertGreaterEqual(total, 2)
        found = [i for i in items if i["queue_entry_id"] == str(paper_entry.id)]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["document_id"], str(paper_doc.id))
        self.assertFalse(found[0]["paper_intake_action_required"])
        self.assertIsNone(found[0]["intake_form_id"])

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

    def test_published_by_user_id_filter(self) -> None:
        publisher = StaffUser.objects.create_user(
            username="cov-publisher-z",
            email="cov.publisher.z@example.com",
            password="x",
            is_staff=True,
            first_name="Zed",
            last_name="UniquePubLastName",
        )
        assign_group_to_test_user(publisher, "Doctor")
        doc = self._make_medical_doc()
        self._make_published_version(doc, published_by_user=publisher)

        items, total = list_doctor_work_queue(
            user=self.doctor, published_by_user_id=publisher.id
        )
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["document_id"], str(doc.id))

        items, total = list_doctor_work_queue(
            user=self.doctor, published_by_user_id=self.doctor.id
        )
        self.assertEqual(total, 0)

    def test_non_assigned_doctor_sees_pending_intake_without_document(self):
        other = StaffUser.objects.create_user(
            username="other-doc",
            email="other-doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        items, total = list_doctor_work_queue(user=other)
        self.assertEqual(total, 1)

    def test_non_assigned_doctor_sees_nothing_when_only_others_published(self):
        self._make_medical_doc()
        other = StaffUser.objects.create_user(
            username="other-doc-2",
            email="other-doc-2@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        items, total = list_doctor_work_queue(user=other)
        self.assertEqual(total, 0)


class ListDoctorWorkQueuePerfTests(ServicesCoverageBase):
    def test_query_count_budget_for_mixed_abc_page(self) -> None:
        digital_entry = QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=Patient.objects.create(
                first_name="Digi",
                last_name="AState",
                date_of_birth=date(1990, 1, 2),
                phone="48500000111",
                email="digia@example.com",
            ),
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=210,
            created_by_user=self.doctor,
            doctor_list_sort_at=timezone.now() - timedelta(minutes=3),
        )
        digital_session = PatientFormSession.objects.create(
            queue_entry=digital_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        digital_intake = PatientIntakeForm.objects.create(
            queue_entry=digital_entry,
            session=digital_session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(minutes=3),
            signature_sha256="a" * 64,
        )
        digital_doc = MedicalDocument.objects.create(
            queue_entry=digital_entry,
            intake_form=digital_intake,
            source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            created_by_user=self.doctor,
        )
        self._make_published_version(digital_doc, version_no=1)

        waiting_paper_entry = QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=Patient.objects.create(
                first_name="Paper",
                last_name="BState",
                date_of_birth=date(1992, 2, 3),
                phone="48500000112",
                email="paperb@example.com",
            ),
            entry_status=QueueEntryStatus.WAITING,
            position_no=211,
            created_by_user=self.doctor,
            doctor_list_sort_at=timezone.now() - timedelta(minutes=2),
            appointment_time=timezone.now() - timedelta(hours=4),
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=waiting_paper_entry,
            authorized_at=timezone.now() - timedelta(minutes=2),
            authorized_by=self.doctor,
            reason="Paper authorization for perf test path B",
        )

        completed_paper_entry = QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=Patient.objects.create(
                first_name="Paper",
                last_name="CState",
                date_of_birth=date(1993, 3, 4),
                phone="48500000113",
                email="paperc@example.com",
            ),
            entry_status=QueueEntryStatus.PAPER_INTAKE_COMPLETED,
            position_no=212,
            created_by_user=self.doctor,
            doctor_list_sort_at=timezone.now() - timedelta(minutes=1),
        )
        completed_doc = MedicalDocument.objects.create(
            queue_entry=completed_paper_entry,
            intake_form=None,
            source_type=MedicalDocumentSourceType.PAPER_INTAKE,
            status=MedicalDocStatus.DRAFT,
            current_version_no=1,
            created_by_user=self.doctor,
        )
        self._make_published_version(
            completed_doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            publish_request_id=None,
            published_at=None,
            publish_locale=None,
        )

        with CaptureQueriesContext(connection) as ctx:
            items, total = list_doctor_work_queue(
                user=self.doctor, page=1, page_size=25
            )

        self.assertGreaterEqual(total, 4)
        self.assertGreaterEqual(len(items), 4)
        self.assertLessEqual(
            len(ctx.captured_queries),
            8,
            msg=f"Expected <=8 SQL queries, got {len(ctx.captured_queries)}",
        )

    def test_benchmark_mixed_population_has_stable_query_count(self) -> None:
        target_rows = 120
        paper_waiting_rows = 6
        paper_completed_rows = 6
        now = timezone.now()
        for i in range(target_rows):
            patient = Patient.objects.create(
                first_name=f"Perf{i}",
                last_name=f"Queue{i}",
                date_of_birth=date(1980, 1, 1),
                phone=f"48999{i:05d}",
                email=f"perf{i}@example.com",
            )
            if i < paper_waiting_rows:
                entry = QueueEntry.objects.create(
                    daily_queue=self.daily_queue,
                    patient=patient,
                    entry_status=QueueEntryStatus.WAITING,
                    position_no=300 + i,
                    created_by_user=self.doctor,
                    appointment_time=now - timedelta(hours=4),
                    doctor_list_sort_at=now - timedelta(minutes=i),
                )
                PaperIntakeAuthorization.objects.create(
                    queue_entry=entry,
                    authorized_at=now - timedelta(minutes=i),
                    authorized_by=self.doctor,
                    reason=f"Perf paper waiting row {i} reason",
                )
                continue

            if i < paper_waiting_rows + paper_completed_rows:
                entry = QueueEntry.objects.create(
                    daily_queue=self.daily_queue,
                    patient=patient,
                    entry_status=QueueEntryStatus.PAPER_INTAKE_COMPLETED,
                    position_no=300 + i,
                    created_by_user=self.doctor,
                    doctor_list_sort_at=now - timedelta(minutes=i),
                )
                doc = MedicalDocument.objects.create(
                    queue_entry=entry,
                    intake_form=None,
                    source_type=MedicalDocumentSourceType.PAPER_INTAKE,
                    status=MedicalDocStatus.DRAFT,
                    current_version_no=1,
                    created_by_user=self.doctor,
                )
                self._make_published_version(
                    doc,
                    version_no=1,
                    version_status=DocVersionStatus.DRAFT,
                    publish_request_id=None,
                    published_at=None,
                    publish_locale=None,
                )
                continue

            entry = QueueEntry.objects.create(
                daily_queue=self.daily_queue,
                patient=patient,
                entry_status=QueueEntryStatus.PATIENT_COMPLETED,
                position_no=300 + i,
                created_by_user=self.doctor,
                doctor_list_sort_at=now - timedelta(minutes=i),
            )
            session = PatientFormSession.objects.create(
                queue_entry=entry,
                form_locale="de-DE",
                expires_at=now + timedelta(hours=1),
                created_by_user=self.doctor,
            )
            intake = PatientIntakeForm.objects.create(
                queue_entry=entry,
                session=session,
                form_status=IntakeStatus.SUBMITTED,
                submitted_at=now - timedelta(minutes=i),
                signature_sha256="a" * 64,
            )
            doc = MedicalDocument.objects.create(
                queue_entry=entry,
                intake_form=intake,
                source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
                status=MedicalDocStatus.DRAFT,
                current_version_no=1,
                created_by_user=self.doctor,
            )
            self._make_published_version(
                doc,
                version_no=1,
                version_status=DocVersionStatus.DRAFT,
                publish_request_id=None,
                published_at=None,
                publish_locale=None,
            )

        start = perf_counter()
        with CaptureQueriesContext(connection) as ctx:
            items, total = list_doctor_work_queue(
                user=self.doctor, page=1, page_size=25
            )
        elapsed_ms = (perf_counter() - start) * 1000

        self.assertEqual(total, target_rows + 1)
        self.assertEqual(len(items), 25)
        # Regression guard: query count should stay constant despite mixed A/B/C population.
        self.assertLessEqual(
            len(ctx.captured_queries),
            8,
            msg=(
                f"Mixed A/B/C benchmark exceeded SQL budget with "
                f"{len(ctx.captured_queries)} queries and {elapsed_ms:.1f} ms."
            ),
        )


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


# ------------------------------------------------------------------
# 7. Document locking services
# ------------------------------------------------------------------
class DocumentLockTests(ServicesCoverageBase):
    def _make_draft_doc(self):
        return MedicalDocument.objects.create(
            queue_entry=self.queue_entry,
            intake_form=self.intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )

    def _other_doctor(self, suffix="lock"):
        user = StaffUser.objects.create_user(
            username=f"cov-{suffix}",
            email=f"cov-{suffix}@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(user, "Doctor")
        return user

    def _admin_user(self):
        user = StaffUser.objects.create_user(
            username="cov-admin-lock",
            email="cov-admin-lock@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(user, "Admin")
        return user

    # -- get_document_lock_state --
    def test_lock_state_no_lock(self):
        doc = self._make_draft_doc()
        eff, name, at = get_document_lock_state(doc)
        self.assertFalse(eff)
        self.assertIsNone(name)
        self.assertIsNone(at)

    def test_lock_state_active_lock(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        eff, name, at = get_document_lock_state(doc)
        self.assertTrue(eff)
        self.assertIsNotNone(name)
        self.assertIsNotNone(at)

    def test_lock_state_expired_lock(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now() - timedelta(
            hours=DOCUMENT_LOCK_TIMEOUT_HOURS + 1
        )
        doc.save(update_fields=["locked_by_user", "locked_at"])
        eff, name, at = get_document_lock_state(doc)
        self.assertFalse(eff)
        self.assertIsNone(name)
        self.assertIsNone(at)

    def test_lock_state_without_user_relation_loaded(self):
        doc = self._make_draft_doc()
        doc.locked_by_user_id = self.doctor.id
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        plain = MedicalDocument.objects.get(id=doc.id)
        eff, name, at = get_document_lock_state(plain)
        self.assertTrue(eff)
        self.assertIsNotNone(name)

    def test_lock_state_resolves_holder_when_instance_has_no_user_relation(
        self,
    ) -> None:
        """``get_document_lock_state`` falls back to ``StaffUser`` lookup when no FK object."""
        ns = SimpleNamespace(
            locked_by_user_id=self.doctor.id,
            locked_at=timezone.now(),
        )
        eff, name, at = get_document_lock_state(ns)  # type: ignore[arg-type]
        self.assertTrue(eff)
        self.assertIsNotNone(name)
        self.assertIsNotNone(at)

    # -- acquire_document_lock --
    def test_acquire_free_lock(self):
        doc = self._make_draft_doc()
        granted, holder = acquire_document_lock(
            medical_document_id=doc.id, user=self.doctor
        )
        self.assertTrue(granted)
        self.assertIsNone(holder)
        doc.refresh_from_db()
        self.assertEqual(doc.locked_by_user_id, self.doctor.id)

    def test_acquire_own_lock_refreshes(self):
        doc = self._make_draft_doc()
        old_time = timezone.now() - timedelta(minutes=30)
        doc.locked_by_user = self.doctor
        doc.locked_at = old_time
        doc.save(update_fields=["locked_by_user", "locked_at"])
        granted, holder = acquire_document_lock(
            medical_document_id=doc.id, user=self.doctor
        )
        self.assertTrue(granted)
        doc.refresh_from_db()
        self.assertGreater(doc.locked_at, old_time)

    def test_acquire_other_lock_denied(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        other = self._other_doctor("acq-deny")
        granted, holder = acquire_document_lock(medical_document_id=doc.id, user=other)
        self.assertFalse(granted)
        self.assertIsNotNone(holder)

    def test_acquire_admin_takes_over(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        admin = self._admin_user()
        granted, holder = acquire_document_lock(medical_document_id=doc.id, user=admin)
        self.assertTrue(granted)
        doc.refresh_from_db()
        self.assertEqual(doc.locked_by_user_id, admin.id)

    def test_acquire_expired_lock_grants(self):
        doc = self._make_draft_doc()
        other = self._other_doctor("acq-exp")
        doc.locked_by_user = other
        doc.locked_at = timezone.now() - timedelta(
            hours=DOCUMENT_LOCK_TIMEOUT_HOURS + 1
        )
        doc.save(update_fields=["locked_by_user", "locked_at"])
        granted, holder = acquire_document_lock(
            medical_document_id=doc.id, user=self.doctor
        )
        self.assertTrue(granted)
        doc.refresh_from_db()
        self.assertEqual(doc.locked_by_user_id, self.doctor.id)

    def test_acquire_on_published_doc_returns_true(self):
        doc = self._make_medical_doc()
        granted, holder = acquire_document_lock(
            medical_document_id=doc.id, user=self.doctor
        )
        self.assertTrue(granted)

    # -- release_document_lock --
    def test_release_own_lock(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        result = release_document_lock(medical_document_id=doc.id, user=self.doctor)
        self.assertTrue(result)
        doc.refresh_from_db()
        self.assertIsNone(doc.locked_by_user_id)

    def test_release_no_lock(self):
        doc = self._make_draft_doc()
        result = release_document_lock(medical_document_id=doc.id, user=self.doctor)
        self.assertTrue(result)

    def test_release_other_lock_denied(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        other = self._other_doctor("rel-deny")
        result = release_document_lock(medical_document_id=doc.id, user=other)
        self.assertFalse(result)

    def test_release_admin_releases_other_lock(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        admin = self._admin_user()
        result = release_document_lock(medical_document_id=doc.id, user=admin)
        self.assertTrue(result)
        doc.refresh_from_db()
        self.assertIsNone(doc.locked_by_user_id)

    # -- refresh_document_lock --
    def test_refresh_own_lock(self):
        doc = self._make_draft_doc()
        old_time = timezone.now() - timedelta(minutes=10)
        doc.locked_by_user = self.doctor
        doc.locked_at = old_time
        doc.save(update_fields=["locked_by_user", "locked_at"])
        result = refresh_document_lock(medical_document_id=doc.id, user=self.doctor)
        self.assertTrue(result)
        doc.refresh_from_db()
        self.assertGreater(doc.locked_at, old_time)

    def test_refresh_free_lock_acquires(self):
        doc = self._make_draft_doc()
        result = refresh_document_lock(medical_document_id=doc.id, user=self.doctor)
        self.assertTrue(result)
        doc.refresh_from_db()
        self.assertEqual(doc.locked_by_user_id, self.doctor.id)

    def test_refresh_other_lock_denied(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        other = self._other_doctor("ref-deny")
        result = refresh_document_lock(medical_document_id=doc.id, user=other)
        self.assertFalse(result)

    def test_refresh_admin_takes_over(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        admin = self._admin_user()
        result = refresh_document_lock(medical_document_id=doc.id, user=admin)
        self.assertTrue(result)
        doc.refresh_from_db()
        self.assertEqual(doc.locked_by_user_id, admin.id)

    def test_refresh_on_published_doc_returns_true(self):
        doc = self._make_medical_doc()
        result = refresh_document_lock(medical_document_id=doc.id, user=self.doctor)
        self.assertTrue(result)

    # -- list_medical_documents lock fields --
    def test_list_medical_documents_includes_lock_fields(self):
        doc = self._make_draft_doc()
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.save(update_fields=["locked_by_user", "locked_at"])
        items, total = list_medical_documents(user=self.doctor)
        self.assertEqual(total, 1)
        item_data = items[0]
        self.assertIsNotNone(item_data.locked_by_user_id)

    # -- list_doctor_work_queue lock fields --
    def test_work_queue_includes_lock_fields_in_output(self):
        doc = self._make_draft_doc()
        MedicalDocumentVersion.objects.create(
            medical_document=doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
        )
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.current_version_no = 1
        doc.save(update_fields=["locked_by_user", "locked_at", "current_version_no"])
        items, total = list_doctor_work_queue(user=self.doctor)
        self.assertGreaterEqual(total, 1)
        item = items[0]
        self.assertIn("locked_by_username", item)
        self.assertIn("locked_at", item)
        self.assertIn("is_locked_by_other", item)
        self.assertIn("published_by", item)
        self.assertIn("row_is_published", item)
        self.assertIn("row_has_edit_semaphore", item)
        self.assertIn("row_is_fully_delivered", item)
        self.assertFalse(item["is_locked_by_other"])
        self.assertTrue(item["row_has_edit_semaphore"])
        self.assertFalse(item["row_is_fully_delivered"])

    def test_work_queue_locked_by_other(self):
        other = self._other_doctor("wq-lock")
        doc = self._make_draft_doc()
        MedicalDocumentVersion.objects.create(
            medical_document=doc,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
        )
        doc.locked_by_user = other
        doc.locked_at = timezone.now()
        doc.current_version_no = 1
        doc.save(update_fields=["locked_by_user", "locked_at", "current_version_no"])
        items, total = list_doctor_work_queue(user=self.doctor)
        self.assertGreaterEqual(total, 1)
        found = [i for i in items if i["document_id"] == str(doc.id)]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["is_locked_by_other"])
        self.assertTrue(found[0]["row_has_edit_semaphore"])

    def test_work_queue_row_fully_delivered_when_pipeline_complete(self):
        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )
        items, total = list_doctor_work_queue(user=self.doctor)
        found = [i for i in items if i["document_id"] == str(doc.id)]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["row_is_fully_delivered"])
        self.assertFalse(found[0]["row_has_edit_semaphore"])

    def test_work_queue_includes_published_by_doctor_name(self):
        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            published_by_user=self.doctor,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )
        items, total = list_doctor_work_queue(user=self.doctor)
        self.assertGreaterEqual(total, 1)
        found = [i for i in items if i["document_id"] == str(doc.id)]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["published_by"])

    def test_work_queue_row_not_fully_delivered_when_sms_pending(self):
        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=False,
        )
        items, total = list_doctor_work_queue(user=self.doctor)
        found = [i for i in items if i["document_id"] == str(doc.id)]
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0]["row_is_fully_delivered"])

    def test_work_queue_keeps_published_status_while_pipeline_is_pending(self):
        doc = self._make_medical_doc()
        self._make_published_version(
            doc,
            pdf_generation_status=PdfStatus.PENDING,
            hidrive_sent=False,
            sms_sent=False,
        )

        items, total = list_doctor_work_queue(user=self.doctor)

        self.assertGreaterEqual(total, 1)
        found = [i for i in items if i["document_id"] == str(doc.id)]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["status"], MedicalDocStatus.PUBLISHED)
        self.assertEqual(found[0]["pdf_generation_status"], PdfStatus.PENDING)
        self.assertEqual(found[0]["hidrive_status"], "PENDING")
        self.assertEqual(found[0]["sms_status"], "PENDING")
        self.assertFalse(found[0]["row_is_fully_delivered"])
        self.assertEqual(found[0]["row_unpublished_urgency"], 0.0)

    # -- list_medical_documents draft visibility for non-assigned doctor --
    def test_list_medical_documents_draft_visible_to_non_assigned(self):
        self._make_draft_doc()
        other = self._other_doctor("list-vis")
        items, total = list_medical_documents(user=other)
        self.assertEqual(total, 1)

    def test_list_medical_documents_published_hidden_from_non_assigned(self):
        self._make_medical_doc()
        other = self._other_doctor("list-hid")
        self.daily_queue.assigned_doctor = self.doctor
        self.daily_queue.save(update_fields=["assigned_doctor"])
        items, total = list_medical_documents(user=other)
        self.assertEqual(total, 0)


# ------------------------------------------------------------------
# work_queue_row_outbound_complete (doctor list green row)
# ------------------------------------------------------------------
class WorkQueueRowOutboundCompleteTests(TestCase):
    def test_true_when_hidrive_sms_flags_lag_but_outbox_processed(self):
        """Matches list badges: PROCESSED outbox counts COMPLETED without denormalized flags."""
        version = SimpleNamespace(
            pdf_generation_status=PdfStatus.COMPLETED,
            hidrive_sent=False,
            sms_sent=False,
        )
        events = {
            OutboxEventType.GENERATE_PDF: SimpleNamespace(
                status=OutboxStatus.PROCESSED
            ),
            OutboxEventType.HIDRIVE_UPLOAD: SimpleNamespace(
                status=OutboxStatus.PROCESSED
            ),
            OutboxEventType.SMS_SEND: SimpleNamespace(status=OutboxStatus.PROCESSED),
        }
        self.assertTrue(
            work_queue_row_outbound_complete(version=version, events_by_type=events)
        )

    def test_true_when_pdf_flags_lag_but_generate_pdf_processed(self):
        version = SimpleNamespace(
            pdf_generation_status=PdfStatus.PENDING,
            hidrive_sent=True,
            sms_sent=True,
        )
        events = {
            OutboxEventType.GENERATE_PDF: SimpleNamespace(
                status=OutboxStatus.PROCESSED
            ),
            OutboxEventType.HIDRIVE_UPLOAD: SimpleNamespace(
                status=OutboxStatus.PROCESSED
            ),
            OutboxEventType.SMS_SEND: SimpleNamespace(status=OutboxStatus.PROCESSED),
        }
        self.assertTrue(
            work_queue_row_outbound_complete(version=version, events_by_type=events)
        )

    def test_false_when_pdf_pending_and_no_processed_generate_pdf_event(self):
        version = SimpleNamespace(
            pdf_generation_status=PdfStatus.PENDING,
            hidrive_sent=True,
            sms_sent=True,
        )
        events = {
            OutboxEventType.HIDRIVE_UPLOAD: SimpleNamespace(
                status=OutboxStatus.PROCESSED
            ),
            OutboxEventType.SMS_SEND: SimpleNamespace(status=OutboxStatus.PROCESSED),
        }
        self.assertFalse(
            work_queue_row_outbound_complete(version=version, events_by_type=events)
        )

    def test_pdf_generation_stage_complete_helper(self):
        v = SimpleNamespace(pdf_generation_status=PdfStatus.COMPLETED)
        self.assertTrue(pdf_generation_stage_complete(v, {}))
        self.assertFalse(pdf_generation_stage_complete(None, {}))
