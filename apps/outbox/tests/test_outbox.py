from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter

from apps.integrations.hidrive import client as hidrive_client
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import ExternalPdfAttachment, ExternalPdfStatus
from apps.medical.services import (
    create_or_get_medical_document,
    publish_document_version,
    save_draft_document_version,
)
from apps.operations.models import AuditEvent
from apps.outbox.hidrive_paths import build_befund_hidrive_path
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.services import process_outbox_events
from apps.core.api_utils import assign_group_to_test_user
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


class OutboxProcessingTests(TestCase):
    def setUp(self) -> None:
        self.doctor_user = StaffUser.objects.create_user(
            username="doctor-outbox",
            email="doctor.outbox@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")

        self.reception_user = StaffUser.objects.create_user(
            username="reception-outbox",
            email="reception.outbox@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
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

    @override_settings(SMSAPI_USE_MOCK="1", HIDRIVE_USE_MOCK="1")
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
        patient_id = str(self.medical_document.queue_entry.patient_id)
        self.assertIn(f"/patients/{patient_id}/", self.version.hidrive_path or "")
        self.assertTrue((self.version.hidrive_path or "").endswith("/Befund_v1.pdf"))

        self.assertEqual(
            OutboxEvent.objects.filter(
                medical_document_version=self.version, status=OutboxStatus.PROCESSED
            ).count(),
            3,
        )

    @override_settings(HIDRIVE_PATIENTS_DIR_PREFIX="/public/patients")
    def test_build_befund_hidrive_path_uses_patients_dir_prefix(self) -> None:
        patient_id = str(self.medical_document.queue_entry.patient_id)
        path = build_befund_hidrive_path(self.version)
        self.assertIn(f"/public/patients/{patient_id}/", path)
        self.assertTrue(path.endswith("/Befund_v1.pdf"))
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="OUTBOX_EVENT_PROCESSED",
                medical_document_id=self.medical_document.id,
            ).count(),
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
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="OUTBOX_EVENT_DEAD_LETTERED",
                outbox_event_id=event.id,
            ).exists()
        )

    @override_settings(SMSAPI_USE_MOCK="1", HIDRIVE_USE_MOCK="1")
    def test_outbox_moves_matched_external_pdf_to_processed_after_upload(self) -> None:
        """§12 pipeline: GENERATE_PDF merges external bytes; HIDRIVE_UPLOAD moves MATCHED rows."""
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        pdf_bytes = _minimal_valid_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file(
            "/incoming/patient_outbox.pdf",
            pdf_bytes,
        )
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_document,
            hidrive_remote_path="/incoming/patient_outbox.pdf",
            original_filename="patient_outbox.pdf",
            status=ExternalPdfStatus.MATCHED,
        )

        first = process_outbox_events()
        second = process_outbox_events()
        third = process_outbox_events()
        self.assertEqual(
            (first.processed, second.processed, third.processed), (1, 1, 1)
        )

        self.version.refresh_from_db()
        self.assertTrue(self.version.hidrive_sent)

        att = ExternalPdfAttachment.objects.get(
            medical_document=self.medical_document,
            original_filename="patient_outbox.pdf",
        )
        self.assertEqual(att.status, ExternalPdfStatus.ACCEPTED)
        self.assertEqual(att.hidrive_remote_path, "/processed/patient_outbox.pdf")

    @override_settings(SMSAPI_USE_MOCK="1", HIDRIVE_USE_MOCK="1")
    def test_outbox_corrupt_external_marks_merge_failed_and_skips_processed_move(
        self,
    ) -> None:
        """§12: invalid HiDrive bytes → MERGE_FAILED; upload still completes; no move to /processed/."""
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        hidrive_client._MockHiDriveAdapter.seed_file(
            "/incoming/patient_outbox.pdf",
            b"%PDF-1.4\nnot-enough-for-reader",
        )
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_document,
            hidrive_remote_path="/incoming/patient_outbox.pdf",
            original_filename="patient_outbox.pdf",
            status=ExternalPdfStatus.MATCHED,
        )

        process_outbox_events()
        process_outbox_events()
        process_outbox_events()

        att = ExternalPdfAttachment.objects.get(
            medical_document=self.medical_document,
            original_filename="patient_outbox.pdf",
        )
        self.assertEqual(att.status, ExternalPdfStatus.MERGE_FAILED)
        self.assertEqual(att.hidrive_remote_path, "/incoming/patient_outbox.pdf")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="EXTERNAL_PDF_CORRUPT",
                medical_document_id=self.medical_document.id,
            ).exists()
        )

    @override_settings(SMSAPI_USE_MOCK="1", HIDRIVE_USE_MOCK="1")
    def test_outbox_missing_external_file_marks_merge_failed_and_still_completes_chain(
        self,
    ) -> None:
        """HiDrive download errors must not fail GENERATE_PDF; Befund-only PDF + upload proceed."""
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_document,
            hidrive_remote_path="/incoming/not_seeded.pdf",
            original_filename="not_seeded.pdf",
            status=ExternalPdfStatus.MATCHED,
        )

        process_outbox_events()
        process_outbox_events()
        process_outbox_events()

        self.version.refresh_from_db()
        self.assertTrue(self.version.hidrive_sent)
        self.assertIsNotNone(self.version.pdf_local_path)

        att = ExternalPdfAttachment.objects.get(
            medical_document=self.medical_document,
            original_filename="not_seeded.pdf",
        )
        self.assertEqual(att.status, ExternalPdfStatus.MERGE_FAILED)
        self.assertEqual(att.hidrive_remote_path, "/incoming/not_seeded.pdf")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="EXTERNAL_PDF_DOWNLOAD_FAILED",
                medical_document_id=self.medical_document.id,
            ).exists()
        )
