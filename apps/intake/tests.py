from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.intake.models import (
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    IntakeOutboxEventType,
    IntakeOutboxStatus,
    IntakePdfStatus,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.outbox_services import process_intake_outbox_events
from apps.intake.services import (
    InvalidSignatureError,
    RequiredAnamnesisMissingError,
    RequiredConsentMissingError,
    IntakeSessionValidationError,
    SIGNATURE_MAX_SIZE,
    _read_signature_data_url,
    _effective_consent_filter,
    _effective_question_filter,
    submit_patient_intake_form,
)
from apps.core.api_utils import assign_group_to_test_user
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
from apps.users.models import StaffUser


class SubmitPatientIntakeFormTests(TestCase):
    def setUp(self) -> None:
        self.reception_user = StaffUser.objects.create_user(
            username="reception-intake",
            email="reception.intake@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
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
        signature_dir = Path(settings.MEDIA_ROOT) / "signatures" / "tests"
        signature_dir.mkdir(parents=True, exist_ok=True)
        signature_path = signature_dir / f"{self.queue_entry.id}.png"
        signature_bytes = b"\x89PNG\r\n\x1a\n" + b"valid-test-signature"
        signature_path.write_bytes(signature_bytes)

        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=self.session,
            form_status=IntakeStatus.IN_PROGRESS,
            signature_file_path=str(signature_path),
            signature_sha256=hashlib.sha256(signature_bytes).hexdigest(),
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
            title_en="Consent",
            content_de="Treść",
            content_en="Content",
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

    def _accept_all_required_consents_effective_today(self) -> None:
        today = timezone.now().date()
        for cdef in ConsentDefinition.objects.filter(
            _effective_consent_filter(today), is_required=True
        ):
            PatientIntakeConsent.objects.get_or_create(
                intake_form=self.intake_form,
                consent_definition=cdef,
                defaults={"accepted": True, "accepted_at": timezone.now()},
            )

    def _ensure_all_required_questions_answered_today(self) -> None:
        today = timezone.now().date()
        required = list(
            AnamnesisQuestionDefinition.objects.filter(
                _effective_question_filter(today), is_required=True
            ).prefetch_related("options")
        )
        answers = list(self.intake_form.anamnesis_payload.get("answers", []))
        answered_codes = {a.get("question_code") for a in answers if a.get("question_code")}
        for q in required:
            if q.code in answered_codes:
                continue
            first_option = next(iter(q.options.order_by("display_order")), None)
            if first_option:
                answers.append({
                    "question_code": q.code,
                    "selected_option_codes": [first_option.code],
                    "free_text": None,
                })
            else:
                answers.append({
                    "question_code": q.code,
                    "selected_option_codes": [],
                    "free_text": "–",
                })
        self.intake_form.anamnesis_payload = {"schema_version": 1, "answers": answers}
        self.intake_form.save(update_fields=["anamnesis_payload", "updated_at"])

    def test_submit_patient_intake_form_success(self) -> None:
        self._accept_all_required_consents_effective_today()
        self._ensure_all_required_questions_answered_today()

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
        intake_version = IntakeDocumentVersion.objects.get(intake_form=self.intake_form)
        self.assertEqual(intake_version.pdf_generation_status, IntakePdfStatus.PENDING)
        self.assertIn("signature", intake_version.snapshot_payload)
        event = IntakeOutboxEvent.objects.get(
            intake_document_version=intake_version,
            event_type=IntakeOutboxEventType.GENERATE_INTAKE_PDF,
        )
        self.assertEqual(event.status, IntakeOutboxStatus.PENDING)

    def test_submit_patient_intake_form_raises_when_required_consent_missing(self) -> None:
        with self.assertRaises(RequiredConsentMissingError):
            submit_patient_intake_form(intake_form_id=self.intake_form.id)

    def test_submit_patient_intake_form_raises_when_required_anamnesis_missing(self) -> None:
        self._accept_all_required_consents_effective_today()
        self.intake_form.anamnesis_payload = {"schema_version": 1, "answers": []}
        self.intake_form.save(update_fields=["anamnesis_payload", "updated_at"])

        with self.assertRaises(RequiredAnamnesisMissingError):
            submit_patient_intake_form(intake_form_id=self.intake_form.id)

    def test_submit_patient_intake_form_raises_when_session_is_not_active(self) -> None:
        self._accept_all_required_consents_effective_today()
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

    @override_settings(HIDRIVE_USE_MOCK="1")
    def test_process_intake_outbox_events_generates_pdf_and_hidrive_upload(self) -> None:
        self._accept_all_required_consents_effective_today()
        self._ensure_all_required_questions_answered_today()
        submitted = submit_patient_intake_form(intake_form_id=self.intake_form.id)
        self.assertEqual(submitted.form_status, IntakeStatus.SUBMITTED)

        first = process_intake_outbox_events()
        second = process_intake_outbox_events()
        self.assertEqual(first.processed, 1)
        self.assertEqual(second.processed, 1)

        version = IntakeDocumentVersion.objects.get(intake_form=self.intake_form)
        version.refresh_from_db()
        self.assertEqual(version.pdf_generation_status, IntakePdfStatus.COMPLETED)
        self.assertTrue(version.hidrive_sent)
        self.assertIsNotNone(version.pdf_local_path)
        patient_id = str(self.queue_entry.patient_id)
        self.assertIn(f"/hidrive/patients/{patient_id}/", version.hidrive_path or "")
        self.assertTrue((version.hidrive_path or "").endswith("/Intake_v1.pdf"))

    def test_submit_is_idempotent_for_already_submitted_form(self) -> None:
        self._accept_all_required_consents_effective_today()
        self._ensure_all_required_questions_answered_today()
        submit_patient_intake_form(intake_form_id=self.intake_form.id)
        submit_patient_intake_form(intake_form_id=self.intake_form.id)
        self.assertEqual(IntakeDocumentVersion.objects.filter(intake_form=self.intake_form).count(), 1)

    def test_read_signature_data_url_rejects_file_extension_content_mismatch(self) -> None:
        signature_dir = Path(settings.MEDIA_ROOT) / "signatures" / "tests"
        signature_dir.mkdir(parents=True, exist_ok=True)
        bad_signature_path = signature_dir / f"{self.queue_entry.id}-bad.jpg"
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"fakepng"
        bad_signature_path.write_bytes(png_bytes)
        self.intake_form.signature_file_path = str(bad_signature_path)
        self.intake_form.signature_sha256 = hashlib.sha256(png_bytes).hexdigest()
        self.intake_form.save(update_fields=["signature_file_path", "signature_sha256", "updated_at"])

        with self.assertRaises(InvalidSignatureError):
            _read_signature_data_url(self.intake_form)

    def test_read_signature_data_url_rejects_oversized_signature_file(self) -> None:
        signature_dir = Path(settings.MEDIA_ROOT) / "signatures" / "tests"
        signature_dir.mkdir(parents=True, exist_ok=True)
        huge_signature_path = signature_dir / f"{self.queue_entry.id}-huge.png"
        huge_signature_path.write_bytes(b"\x89PNG\r\n\x1a\n" + (b"a" * (SIGNATURE_MAX_SIZE + 1)))
        self.intake_form.signature_file_path = str(huge_signature_path)
        self.intake_form.signature_sha256 = hashlib.sha256(huge_signature_path.read_bytes()).hexdigest()
        self.intake_form.save(update_fields=["signature_file_path", "signature_sha256", "updated_at"])

        with self.assertRaises(InvalidSignatureError):
            _read_signature_data_url(self.intake_form)
