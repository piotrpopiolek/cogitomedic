from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.intake.models import (
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.services import (
    RequiredAnamnesisMissingError,
    RequiredConsentMissingError,
    IntakeSessionValidationError,
    submit_patient_intake_form,
)
from apps.operations.models import AuditEvent
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


class SubmitPatientIntakeFormTests(TestCase):
    def setUp(self) -> None:
        self.reception_user = StaffUser.objects.create_user(
            username="reception-intake",
            email="reception.intake@example.com",
            password="safe-password",
            role=StaffRole.RECEPTION,
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="WAW", name="Warsaw")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="A1", name="A1")
        daily_queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Intake",
            last_name="Patient",
            date_of_birth=date(1990, 2, 2),
            phone="+48123456789",
            email="intake.patient@example.com",
            doctolib_patient_id="DOC-IN-1",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=1,
            created_by_user=self.reception_user,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
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
            anamnesis_payload={
                "answers": [
                    {
                        "question_code": "Q1_REQUIRED",
                        "selected_option_codes": ["YES"],
                    }
                ]
            },
        )

        self.required_consent = ConsentDefinition.objects.create(
            code="CONSENT_REQUIRED",
            version=1,
            title_de="Einwilligung",
            content_de="Treść",
            is_required=True,
            is_active=True,
        )
        self.required_question = AnamnesisQuestionDefinition.objects.create(
            code="Q1_REQUIRED",
            version=1,
            question_text_de="Frage",
            question_text_en="Question",
            is_required=True,
            is_active=True,
        )

    def test_submit_patient_intake_form_success(self) -> None:
        PatientIntakeConsent.objects.create(
            intake_form=self.intake_form,
            consent_definition=self.required_consent,
            accepted=True,
            accepted_at=timezone.now(),
        )

        submitted = submit_patient_intake_form(intake_form_id=self.intake_form.id)

        submitted.refresh_from_db()
        self.session.refresh_from_db()
        self.queue_entry.refresh_from_db()

        self.assertEqual(submitted.form_status, IntakeStatus.SUBMITTED)
        self.assertIsNotNone(submitted.submitted_at)
        self.assertIsNotNone(self.session.consumed_at)
        self.assertEqual(self.queue_entry.entry_status, QueueEntryStatus.PATIENT_COMPLETED)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="INTAKE_SUBMITTED",
                patient_id=self.queue_entry.patient_id,
            ).exists()
        )

    def test_submit_patient_intake_form_raises_when_required_consent_missing(self) -> None:
        with self.assertRaises(RequiredConsentMissingError):
            submit_patient_intake_form(intake_form_id=self.intake_form.id)

    def test_submit_patient_intake_form_raises_when_required_anamnesis_missing(self) -> None:
        PatientIntakeConsent.objects.create(
            intake_form=self.intake_form,
            consent_definition=self.required_consent,
            accepted=True,
            accepted_at=timezone.now(),
        )
        self.intake_form.anamnesis_payload = {"answers": []}
        self.intake_form.save(update_fields=["anamnesis_payload", "updated_at"])

        with self.assertRaises(RequiredAnamnesisMissingError):
            submit_patient_intake_form(intake_form_id=self.intake_form.id)

    def test_submit_patient_intake_form_raises_when_session_is_not_active(self) -> None:
        PatientIntakeConsent.objects.create(
            intake_form=self.intake_form,
            consent_definition=self.required_consent,
            accepted=True,
            accepted_at=timezone.now(),
        )
        newer_session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=self.reception_user,
        )
        self.queue_entry.active_session = newer_session
        self.queue_entry.save(update_fields=["active_session", "updated_at"])

        with self.assertRaises(IntakeSessionValidationError):
            submit_patient_intake_form(intake_form_id=self.intake_form.id)
