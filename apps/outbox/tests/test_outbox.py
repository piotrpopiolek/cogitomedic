from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from uuid import uuid4

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter
from unittest.mock import MagicMock, patch

from apps.core.exceptions import DomainError
from apps.integrations.hidrive import client as hidrive_client
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    PdfStatus,
)
from apps.medical.services import (
    create_or_get_medical_document,
    publish_document_version,
    save_draft_document_version,
)
from apps.operations.models import AuditEvent
from apps.outbox.hidrive_paths import build_befund_hidrive_path
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox import services as outbox_services
from apps.outbox.services import process_outbox_events
from apps.operations.prom_metrics import build_metrics_payload
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

        payload = build_metrics_payload()
        self.assertIn(b"cogitomedica_outbox_processing_duration_seconds_sum", payload)
        self.assertIn(b"cogitomedica_outbox_events_total", payload)

    @override_settings(SMSAPI_USE_MOCK="1", HIDRIVE_USE_MOCK="1")
    @patch("apps.outbox.services.get_sms_adapter")
    def test_republished_version_sms_sent_when_prior_version_notified(
        self, mock_get_sms: MagicMock
    ) -> None:
        mock_sms = MagicMock()
        mock_get_sms.return_value = mock_sms

        for _ in range(3):
            process_outbox_events()
        self.version.refresh_from_db()
        self.assertTrue(self.version.sms_sent)
        v1_sms_at = self.version.sms_sent_at
        self.assertEqual(mock_sms.send_sms.call_count, 1)

        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "rev": 2},
            intent="amend",
        )
        v2 = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )

        for _ in range(12):
            result = process_outbox_events()
            if result.processed == 0:
                break

        v2.refresh_from_db()
        self.assertTrue(v2.hidrive_sent)
        self.assertTrue(v2.sms_sent)
        self.assertEqual(v2.sms_sent_at, v1_sms_at)
        self.assertEqual(mock_sms.send_sms.call_count, 1)

    def test_execute_event_internal_sets_span_attributes_when_recording(self) -> None:
        event = OutboxEvent.objects.get(
            medical_document_version=self.version,
            event_type=OutboxEventType.GENERATE_PDF,
        )
        event.payload = {"simulate_error": True}
        event.save(update_fields=["payload"])
        with patch.object(outbox_services.trace, "get_current_span") as gsm:
            mock_span = MagicMock()
            mock_span.is_recording.return_value = True
            gsm.return_value = mock_span
            with transaction.atomic():
                with self.assertRaises(RuntimeError):
                    outbox_services._execute_event_internal(event, now=timezone.now())
        mock_span.set_attribute.assert_any_call(
            "cogito.medical_document_id", str(self.medical_document.id)
        )
        mock_span.set_attribute.assert_any_call(
            "cogito.intake_form_id", str(self.medical_document.intake_form_id)
        )

    @override_settings(HIDRIVE_PATIENTS_DIR_PREFIX="/public/patients")
    def test_build_befund_hidrive_path_uses_patients_dir_prefix(self) -> None:
        patient_id = str(self.medical_document.queue_entry.patient_id)
        path = build_befund_hidrive_path(self.version)
        self.assertIn(f"/public/patients/{patient_id}/", path)
        self.assertTrue(path.endswith("/Befund_v1.pdf"))

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

    def test_external_upload_generate_pdf_invariant_domain_error_dead_letters_immediately(
        self,
    ) -> None:
        MedicalDocument.objects.filter(pk=self.medical_document.pk).update(
            source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD
        )
        event = OutboxEvent.objects.get(
            medical_document_version=self.version,
            event_type=OutboxEventType.GENERATE_PDF,
        )
        event.payload = {}
        event.max_retries = 10
        event.retry_count = 0
        event.status = OutboxStatus.PENDING
        event.available_at = timezone.now() - timedelta(seconds=5)
        event.save(
            update_fields=[
                "payload",
                "max_retries",
                "retry_count",
                "status",
                "available_at",
                "updated_at",
            ]
        )
        OutboxEvent.objects.filter(medical_document_version=self.version).exclude(
            id=event.id
        ).delete()
        with patch(
            "apps.outbox.services.generate_external_upload_pdf",
            side_effect=DomainError(
                "no attachment",
                api_message_key="other.domain.external_upload_generate_pdf_no_attachment",
            ),
        ):
            result = process_outbox_events()
        event.refresh_from_db()
        self.assertEqual(result.dead_lettered, 1)
        self.assertEqual(event.status, OutboxStatus.DEAD_LETTER)
        self.assertGreaterEqual(event.retry_count, event.max_retries)

    def test_failed_outbox_event_persists_when_record_outbox_execution_raises(
        self,
    ) -> None:
        """Metrics must not abort @transaction.atomic batch or roll back failure handling."""
        event = OutboxEvent.objects.get(
            medical_document_version=self.version,
            event_type=OutboxEventType.GENERATE_PDF,
        )
        event.payload = {"simulate_error": True}
        event.max_retries = 10
        event.retry_count = 0
        event.status = OutboxStatus.PENDING
        event.available_at = timezone.now() - timedelta(seconds=5)
        event.save(
            update_fields=[
                "payload",
                "max_retries",
                "retry_count",
                "status",
                "available_at",
                "updated_at",
            ]
        )
        with patch.object(
            outbox_services,
            "record_outbox_execution",
            side_effect=RuntimeError("metrics unavailable"),
        ):
            result = process_outbox_events()
        self.assertEqual(result.failed, 1)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.FAILED)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="OUTBOX_EVENT_FAILED",
                outbox_event_id=event.id,
            ).exists()
        )

    @override_settings(
        SMSAPI_USE_MOCK="1",
        HIDRIVE_USE_MOCK="1",
        HIDRIVE_INCOMING_PATH="/incoming",
        HIDRIVE_PROCESSED_PATH="/processed",
        HIDRIVE_PATIENTS_DIR_PREFIX="/patients",
    )
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

    @override_settings(
        SMSAPI_USE_MOCK="1",
        HIDRIVE_USE_MOCK="1",
        HIDRIVE_INCOMING_PATH="/incoming",
        HIDRIVE_PROCESSED_PATH="/processed",
        HIDRIVE_PATIENTS_DIR_PREFIX="/patients",
    )
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

    @override_settings(
        SMSAPI_USE_MOCK="1",
        HIDRIVE_USE_MOCK="1",
        HIDRIVE_INCOMING_PATH="/incoming",
        HIDRIVE_PROCESSED_PATH="/processed",
        HIDRIVE_PATIENTS_DIR_PREFIX="/patients",
        OUTBOX_BASE_BACKOFF_SECONDS=0,
    )
    def test_outbox_missing_external_lab_pdf_fails_then_completes_when_file_arrives(
        self,
    ) -> None:
        """GENERATE_PDF must not store Befund-only when lab PDF is required but missing; retry after upload."""
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        ExternalPdfAttachment.objects.create(
            medical_document=self.medical_document,
            hidrive_remote_path="/incoming/not_seeded.pdf",
            original_filename="not_seeded.pdf",
            status=ExternalPdfStatus.MATCHED,
        )

        r1 = process_outbox_events()
        self.assertEqual(r1.failed, 1)
        self.assertEqual(r1.processed, 0)

        self.version.refresh_from_db()
        self.assertEqual(self.version.pdf_generation_status, PdfStatus.FAILED)
        self.assertFalse(self.version.hidrive_sent)
        self.assertIsNone(self.version.pdf_local_path)

        att = ExternalPdfAttachment.objects.get(
            medical_document=self.medical_document,
            original_filename="not_seeded.pdf",
        )
        self.assertEqual(att.status, ExternalPdfStatus.MATCHED)
        self.assertEqual(att.hidrive_remote_path, "/incoming/not_seeded.pdf")
        failed_audits = AuditEvent.objects.filter(
            event_type="EXTERNAL_PDF_DOWNLOAD_FAILED",
            medical_document_id=self.medical_document.id,
        )
        self.assertEqual(failed_audits.count(), 1)

        process_outbox_events()
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="EXTERNAL_PDF_DOWNLOAD_FAILED",
                medical_document_id=self.medical_document.id,
            ).count(),
            1,
        )

        pdf_bytes = _minimal_valid_pdf_bytes()
        hidrive_client._MockHiDriveAdapter.seed_file(
            "/incoming/not_seeded.pdf",
            pdf_bytes,
        )

        for _ in range(6):
            process_outbox_events()

        self.version.refresh_from_db()
        self.assertTrue(self.version.hidrive_sent)
        self.assertIsNotNone(self.version.pdf_local_path)
        att.refresh_from_db()
        self.assertEqual(att.status, ExternalPdfStatus.ACCEPTED)
        self.assertEqual(att.hidrive_remote_path, "/processed/not_seeded.pdf")
