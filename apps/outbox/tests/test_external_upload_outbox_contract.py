"""EXTERNAL_UPLOAD outbox: GENERATE_PDF before HIDRIVE materialization; full chain order."""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from io import BytesIO
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter

from apps.core.api_utils import assign_group_to_test_user
from apps.integrations.hidrive import client as hidrive_client
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.medical.services import (
    create_external_upload_medical_document,
    publish_external_upload_version,
    select_external_upload_attachment_for_draft,
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


def _minimal_valid_pdf_bytes() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


@override_settings(
    SMSAPI_USE_MOCK="1",
    HIDRIVE_USE_MOCK="1",
    HIDRIVE_INCOMING_PATH="/incoming",
    HIDRIVE_PROCESSED_PATH="/processed",
    HIDRIVE_PATIENTS_DIR_PREFIX="/patients",
)
class ExternalUploadOutboxContractTests(TestCase):
    def setUp(self) -> None:
        self._media = tempfile.TemporaryDirectory()
        self.addCleanup(self._media.cleanup)
        self.media_root = self._media.name

        self.reception_user = StaffUser.objects.create_user(
            username="ext-outbox-rec",
            email="ext.outbox.rec@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")

    def _fresh_external_upload_document(self):
        clinic = ClinicSite.objects.create(
            code=f"EO{uuid4().hex[:4]}",
            name="Ext Outbox Clinic",
        )
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="E1", name="E1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Ext",
            last_name="Outbox",
            date_of_birth=date(1991, 4, 4),
            phone="+48500111999",
            email=f"ext.outbox.{uuid4().hex[:8]}@example.com",
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
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        PatientIntakeForm.objects.create(
            queue_entry=queue_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        return create_external_upload_medical_document(
            queue_entry_id=queue_entry.id,
            created_by_user_id=self.reception_user.id,
        )

    def test_after_publish_only_generate_pdf_event_exists(self) -> None:
        ext_doc = self._fresh_external_upload_document()
        pdf = _minimal_valid_pdf_bytes()
        path = "/incoming/external-upload/contract.pdf"
        hidrive_client._MockHiDriveAdapter.seed_file(path, pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=ext_doc,
            hidrive_remote_path=path,
            original_filename="contract.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        select_external_upload_attachment_for_draft(
            medical_document_id=ext_doc.id,
            attachment_id=att.id,
            actor_user_id=self.reception_user.id,
        )
        publish_external_upload_version(
            medical_document_id=ext_doc.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.reception_user.id,
            publish_locale="de-DE",
        )
        v = MedicalDocumentVersion.objects.get(
            medical_document=ext_doc,
            version_status=DocVersionStatus.PUBLISHED,
        )
        self.assertEqual(v.pdf_generation_status, PdfStatus.PENDING)
        self.assertFalse(
            OutboxEvent.objects.filter(
                event_type=OutboxEventType.HIDRIVE_UPLOAD
            ).exists()
        )
        types = list(
            OutboxEvent.objects.filter(medical_document_version=v)
            .order_by("created_at")
            .values_list("event_type", flat=True)
        )
        self.assertEqual(types, [OutboxEventType.GENERATE_PDF])

    def test_full_chain_generate_pdf_then_hidrive_then_sms(self) -> None:
        ext_doc = self._fresh_external_upload_document()
        pdf = _minimal_valid_pdf_bytes()
        path = "/incoming/external-upload/chain.pdf"
        hidrive_client._MockHiDriveAdapter.seed_file(path, pdf)
        att = ExternalPdfAttachment.objects.create(
            medical_document=ext_doc,
            hidrive_remote_path=path,
            original_filename="chain.pdf",
            status=ExternalPdfStatus.MATCHED,
        )
        select_external_upload_attachment_for_draft(
            medical_document_id=ext_doc.id,
            attachment_id=att.id,
            actor_user_id=self.reception_user.id,
        )
        publish_external_upload_version(
            medical_document_id=ext_doc.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.reception_user.id,
            publish_locale="de-DE",
        )
        v = MedicalDocumentVersion.objects.get(
            medical_document=ext_doc,
            version_status=DocVersionStatus.PUBLISHED,
        )

        with self.settings(MEDIA_ROOT=self.media_root):
            first = process_outbox_events()
            second = process_outbox_events()
            third = process_outbox_events()

        self.assertEqual(
            (first.processed, second.processed, third.processed), (1, 1, 1)
        )

        v.refresh_from_db()
        self.assertEqual(v.pdf_generation_status, PdfStatus.COMPLETED)
        self.assertTrue(v.pdf_local_path)
        self.assertTrue(v.hidrive_sent)
        self.assertTrue(v.sms_sent)

        events = list(
            OutboxEvent.objects.filter(medical_document_version=v).order_by(
                "created_at"
            )
        )
        self.assertEqual(len(events), 3)
        self.assertEqual(
            [e.event_type for e in events],
            [
                OutboxEventType.GENERATE_PDF,
                OutboxEventType.HIDRIVE_UPLOAD,
                OutboxEventType.SMS_SEND,
            ],
        )
        self.assertEqual(
            [e.status for e in events],
            [OutboxStatus.PROCESSED, OutboxStatus.PROCESSED, OutboxStatus.PROCESSED],
        )
