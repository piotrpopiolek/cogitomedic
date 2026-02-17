from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.intake.models import AnamnesisQuestionDefinition, ConsentDefinition, IntakeStatus, PatientIntakeConsent, PatientIntakeForm
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


class IntakeApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception_user = StaffUser.objects.create_user(
            username="api-reception",
            email="api.reception@example.com",
            password="safe-password",
            role=StaffRole.RECEPTION,
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="API", name="API Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="A1", name="A1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Api",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="+48123456789",
            email="api.patient@example.com",
            doctolib_patient_id="DOC-API-1",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=1,
            created_by_user=self.reception_user,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            token_hash="a" * 64,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=self.reception_user,
        )
        self.queue_entry.active_session = self.session
        self.queue_entry.save(update_fields=["active_session", "updated_at"])
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=self.session,
            form_status=IntakeStatus.IN_PROGRESS,
            signature_file_path="/tmp/signature.png",
            signature_sha256="b" * 64,
            anamnesis_payload={"schema_version": 1, "answers": []},
        )

        self.required_consent = ConsentDefinition.objects.create(
            code="CONSENT_REQUIRED",
            version=1,
            title_de="Einwilligung",
            content_de="Treść",
            is_required=True,
            is_active=True,
        )
        AnamnesisQuestionDefinition.objects.create(
            code="Q1_REQUIRED",
            version=1,
            question_text_de="Frage",
            question_text_en="Question",
            is_required=True,
            is_active=True,
        )

    def test_create_queue_entry_session_endpoint(self) -> None:
        response = self.client.post(
            f"/api/v1/queue-entries/{self.queue_entry.id}/sessions",
            data=json.dumps(
                {
                    "created_by_user_id": str(self.reception_user.id),
                    "form_locale": "en-GB",
                    "expires_in_minutes": 10,
                }
            ),
            content_type="application/json",
        )
        payload = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", payload)
        self.assertIn("session_id", payload)

    def test_update_anamnesis_validation_error_without_schema_version(self) -> None:
        response = self.client.put(
            f"/api/v1/intake-forms/{self.intake_form.id}/anamnesis",
            data=json.dumps({"answers": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_update_anamnesis_success(self) -> None:
        response = self.client.put(
            f"/api/v1/intake-forms/{self.intake_form.id}/anamnesis",
            data=json.dumps(
                {
                    "anamnesis_schema_version": 1,
                    "answers": [{"question_code": "Q1_REQUIRED", "selected_option_codes": ["YES"]}],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.intake_form.refresh_from_db()
        self.assertEqual(self.intake_form.anamnesis_schema_version, 1)
        self.assertEqual(self.intake_form.anamnesis_payload.get("schema_version"), 1)

    def test_submit_intake_success(self) -> None:
        PatientIntakeConsent.objects.create(
            intake_form=self.intake_form,
            consent_definition=self.required_consent,
            accepted=True,
            accepted_at=timezone.now(),
        )
        self.intake_form.anamnesis_payload = {
            "schema_version": 1,
            "answers": [{"question_code": "Q1_REQUIRED", "selected_option_codes": ["YES"]}],
        }
        self.intake_form.save(update_fields=["anamnesis_payload", "updated_at"])

        response = self.client.post(
            f"/api/v1/intake-forms/{self.intake_form.id}/submit",
            data=json.dumps({"submitted_by_user_id": str(self.reception_user.id)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.intake_form.refresh_from_db()
        self.queue_entry.refresh_from_db()
        self.assertEqual(self.intake_form.form_status, IntakeStatus.SUBMITTED)
        self.assertEqual(self.queue_entry.entry_status, QueueEntryStatus.PATIENT_COMPLETED)
