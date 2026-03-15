from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.services import create_or_get_medical_document, publish_document_version, save_draft_document_version
from apps.outbox.models import OutboxStatus
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


class ObservabilityHealthApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.doctor_user = StaffUser.objects.create_user(
            username="health-doctor",
            email="health.doctor@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")
        
        self.reception_user = StaffUser.objects.create_user(
            username="health-reception",
            email="health.reception@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        
        self.admin_user = StaffUser.objects.create_user(
            username="health-admin",
            email="health.admin@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.client.login(username="health-admin", password="safe-password")
        clinic = ClinicSite.objects.create(code="HEA", name="Health")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="H1", name="H1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Health",
            last_name="Patient",
            date_of_birth=date(1991, 1, 1),
            phone="+48123123123",
            email="health.patient@example.com",
            doctolib_patient_id="DOC-H-1",
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
            signature_sha256="x" * 64,
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
        self.version = publish_document_version(
            medical_document_id=medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/api/v1/observability/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("checks", payload)
        self.assertEqual(payload["checks"]["db"], "ok")
        self.assertEqual(payload["checks"]["hidrive"], "unknown")
        self.assertEqual(payload["checks"]["sms"], "unknown")

    def test_health_anonymous_returns_minimal_payload(self) -> None:
        anonymous = Client()
        response = anonymous.get("/api/v1/observability/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("checks", payload)

    def test_metrics_endpoint_returns_prometheus_payload(self) -> None:
        response = self.client.get("/api/v1/observability/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])
        content = response.content.decode("utf-8")
        self.assertIn("cogitomedica_outbox_events_total", content)
        self.assertIn("cogitomedica_outbox_pending_age_seconds", content)
        self.assertIn("cogitomedica_outbox_processing_duration_seconds_sum", content)
        self.assertIn("cogitomedica_outbox_processing_duration_seconds_count", content)
        self.assertIn("cogitomedica_import_batches_total", content)
        self.assertIn("cogitomedica_import_rows_total", content)

    def test_health_and_metrics_return_json_error_for_method_not_allowed(self) -> None:
        health = self.client.post("/api/v1/observability/health", data="{}", content_type="application/json")
        metrics = self.client.post("/api/v1/observability/metrics", data="{}", content_type="application/json")

        self.assertEqual(health.status_code, 405)
        self.assertEqual(metrics.status_code, 405)
        self.assertEqual(health.json()["error"], "Method not allowed.")
        self.assertEqual(metrics.json()["error"], "Method not allowed.")
