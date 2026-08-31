from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.intake.models import (
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.services import (
    get_intake_form_context,
    submit_patient_intake_form,
)
from apps.reception.admin import QueueEntryAdmin
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
from apps.reception.process_types import ProcessType
from apps.reception.services import create_queue_entry
from apps.users.models import StaffUser


def _request_with_messages(user: StaffUser):
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.middleware import SessionMiddleware

    request = RequestFactory().post("/admin/reception/queueentry/")
    request.user = user
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


class QueueEntryProcessTypeTests(TestCase):
    def setUp(self) -> None:
        self.user = StaffUser.objects.create_user(
            username="process-type-reception",
            email="pt.reception@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.user, "Reception")
        self.clinic = ClinicSite.objects.create(code="PT", name="Process Type Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="PT1", name="PT1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.user,
        )
        self.patient = Patient.objects.create(
            first_name="Erika",
            last_name="Mustermann",
            date_of_birth=date(1991, 1, 1),
            phone="+48777888901",
            email="erika.pt@example.com",
        )

    def test_create_defaults_to_standard(self) -> None:
        entry = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
        )
        self.assertEqual(entry.process_type, ProcessType.STANDARD)
        self.assertIsNone(entry.visit_external_id)

    def test_second_same_process_type_raises_domain_error(self) -> None:
        create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        with self.assertRaises(DomainError) as ctx:
            create_queue_entry(
                daily_queue_id=self.queue.id,
                patient_id=self.patient.id,
                created_by_user_id=self.user.id,
                process_type=ProcessType.STANDARD,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.queue_entry_process_type_exists",
        )

    def test_standard_then_telederm_creates_two_entries(self) -> None:
        standard = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        telederm = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.TELEDERM,
        )
        self.assertNotEqual(standard.id, telederm.id)
        self.assertEqual(standard.position_no, 1)
        self.assertEqual(telederm.position_no, 2)
        self.assertIsNone(standard.visit_external_id)
        self.assertIsNone(telederm.visit_external_id)

    def test_unique_constraint_rejects_duplicate_non_cancelled(self) -> None:
        QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=self.patient,
            position_no=1,
            created_by_user=self.user,
            process_type=ProcessType.STANDARD,
        )
        with self.assertRaises(IntegrityError):
            QueueEntry.objects.create(
                daily_queue=self.queue,
                patient=self.patient,
                position_no=2,
                created_by_user=self.user,
                process_type=ProcessType.STANDARD,
            )

    def test_cancelled_standard_allows_new_standard(self) -> None:
        first = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        first.entry_status = QueueEntryStatus.CANCELLED
        first.save(update_fields=["entry_status", "updated_at"])
        second = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(second.process_type, ProcessType.STANDARD)

    def test_process_type_is_immutable(self) -> None:
        entry = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
        )
        entry.process_type = ProcessType.TELEDERM
        with self.assertRaises(ValidationError):
            entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.process_type, ProcessType.STANDARD)

    def test_invalid_process_type_raises(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_queue_entry(
                daily_queue_id=self.queue.id,
                patient_id=self.patient.id,
                created_by_user_id=self.user.id,
                process_type="VIDEO",
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.domain.invalid_process_type"
        )


class QueueEntryProcessTypeApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = StaffUser.objects.create_user(
            username="process-type-api",
            email="pt.api@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.user, "Reception")
        self.clinic = ClinicSite.objects.create(code="PA", name="PT API Clinic")
        self.user.clinic_sites.add(self.clinic)
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="PA1", name="PA1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.user,
        )
        self.patient = Patient.objects.create(
            first_name="Api",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="+48123456001",
            email="pt.api.patient@example.com",
        )
        self.client.login(username="process-type-api", password="safe-password")

    def _post(self, payload: dict):
        return self.client.post(
            f"/api/v1/daily-queues/{self.queue.id}/entries",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_post_defaults_to_standard(self) -> None:
        response = self._post(
            {
                "patient_id": str(self.patient.id),
                "created_by_user_id": str(self.user.id),
            }
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["process_type"], ProcessType.STANDARD)

    def test_post_telederm_then_second_telederm_409(self) -> None:
        payload = {
            "patient_id": str(self.patient.id),
            "created_by_user_id": str(self.user.id),
            "process_type": ProcessType.TELEDERM,
        }
        first = self._post(payload)
        self.assertEqual(first.status_code, 201)
        second = self._post(payload)
        self.assertEqual(second.status_code, 409)

    def test_post_invalid_process_type_400(self) -> None:
        response = self._post(
            {
                "patient_id": str(self.patient.id),
                "created_by_user_id": str(self.user.id),
                "process_type": "VIDEO",
            }
        )
        self.assertEqual(response.status_code, 400)


class QueueEntryProcessTypeAdminTests(TestCase):
    def setUp(self) -> None:
        self.user = StaffUser.objects.create_user(
            username="process-type-admin",
            email="pt.admin@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.user, "Reception")
        self.clinic = ClinicSite.objects.create(code="PAD", name="PT Admin Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="PAD1", name="PAD1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.user,
        )
        self.patient = Patient.objects.create(
            first_name="Admin",
            last_name="Patient",
            date_of_birth=date(1988, 2, 2),
            phone="+48123456002",
            email="pt.admin.patient@example.com",
        )

    def test_admin_create_uses_create_queue_entry(self) -> None:
        obj = QueueEntry(
            daily_queue=self.queue,
            patient=self.patient,
            created_by_user=self.user,
            process_type=ProcessType.TELEDERM,
        )
        form = type(
            "BoundQueueEntryForm",
            (),
            {"changed_data": [], "cleaned_data": {}},
        )()
        QueueEntryAdmin(QueueEntry, AdminSite()).save_model(
            _request_with_messages(self.user), obj, form, False
        )
        obj.refresh_from_db()
        self.assertEqual(obj.process_type, ProcessType.TELEDERM)
        self.assertEqual(obj.position_no, 1)

    def test_admin_create_rejects_duplicate_process_type(self) -> None:
        create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        obj = QueueEntry(
            daily_queue=self.queue,
            patient=self.patient,
            created_by_user=self.user,
            process_type=ProcessType.STANDARD,
        )
        form = type(
            "BoundQueueEntryForm",
            (),
            {"changed_data": [], "cleaned_data": {}},
        )()
        with self.assertRaises(DomainError):
            QueueEntryAdmin(QueueEntry, AdminSite()).save_model(
                _request_with_messages(self.user), obj, form, False
            )


class IntakeProcessTypeCatalogTests(TestCase):
    def setUp(self) -> None:
        self.user = StaffUser.objects.create_user(
            username="process-type-intake",
            email="pt.intake@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.user, "Reception")
        clinic = ClinicSite.objects.create(code="PI", name="PT Intake Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="PI1", name="PI1")
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.user,
        )
        self.patient = Patient.objects.create(
            first_name="Intake",
            last_name="PT",
            date_of_birth=date(1992, 3, 3),
            phone="+48123456003",
            email="pt.intake.patient@example.com",
        )
        self.standard_only = ConsentDefinition.objects.create(
            code="PT_STANDARD_ONLY",
            version=1,
            title_de="Nur A",
            title_en="Standard only",
            content_de="A",
            content_en="A",
            is_required=True,
            process_types=[ProcessType.STANDARD],
        )
        self.both = ConsentDefinition.objects.create(
            code="PT_BOTH",
            version=1,
            title_de="A und B",
            title_en="Both",
            content_de="AB",
            content_en="AB",
            is_required=True,
            process_types=[ProcessType.STANDARD, ProcessType.TELEDERM],
        )
        self.question_a = AnamnesisQuestionDefinition.objects.create(
            code="PT_Q_A",
            version=1,
            question_text_de="Frage A",
            question_text_en="Question A",
            is_required=True,
            process_types=[ProcessType.STANDARD],
        )

    def _intake_for(self, process_type: str) -> PatientIntakeForm:
        entry = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=process_type,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            created_by_user=self.user,
        )
        entry.active_session = session
        entry.save(update_fields=["active_session", "updated_at"])
        signature_dir = Path(settings.MEDIA_ROOT) / "signatures" / "tests"
        signature_dir.mkdir(parents=True, exist_ok=True)
        signature_path = signature_dir / f"{entry.id}.png"
        signature_bytes = b"\x89PNG\r\n\x1a\n" + b"pt-signature"
        signature_path.write_bytes(signature_bytes)
        return PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
            signature_file_path=str(signature_path),
            signature_sha256=hashlib.sha256(signature_bytes).hexdigest(),
            anamnesis_payload={"schema_version": 1, "answers": []},
        )

    def test_standard_context_includes_standard_catalog_not_telederm_only(
        self,
    ) -> None:
        intake = self._intake_for(ProcessType.STANDARD)
        ctx = get_intake_form_context(intake_form_id=intake.id, form_locale="de-DE")
        codes = {c["code"] for c in ctx["consents"]}
        self.assertIn("PT_STANDARD_ONLY", codes)
        self.assertIn("PT_BOTH", codes)
        question_codes = {q["question_code"] for q in ctx["anamnesis_questions"]}
        self.assertIn("PT_Q_A", question_codes)
        self.assertEqual(ctx["process_type"], ProcessType.STANDARD)

    def test_telederm_context_excludes_standard_only_catalog(self) -> None:
        intake = self._intake_for(ProcessType.TELEDERM)
        ctx = get_intake_form_context(intake_form_id=intake.id, form_locale="de-DE")
        codes = {c["code"] for c in ctx["consents"]}
        self.assertNotIn("PT_STANDARD_ONLY", codes)
        self.assertIn("PT_BOTH", codes)
        question_codes = {q["question_code"] for q in ctx["anamnesis_questions"]}
        self.assertNotIn("PT_Q_A", question_codes)
        self.assertEqual(ctx["process_type"], ProcessType.TELEDERM)

    def test_get_and_submit_use_the_same_consent_filter(self) -> None:
        intake = self._intake_for(ProcessType.TELEDERM)
        ctx = get_intake_form_context(intake_form_id=intake.id, form_locale="de-DE")
        required_from_get = {
            c["consent_definition_id"] for c in ctx["consents"] if c["is_required"]
        }
        for consent in ctx["consents"]:
            if consent["is_required"]:
                PatientIntakeConsent.objects.create(
                    intake_form=intake,
                    consent_definition_id=consent["consent_definition_id"],
                    accepted=True,
                    accepted_at=timezone.now(),
                )
        submit_patient_intake_form(intake_form_id=intake.id)
        intake.refresh_from_db()
        self.assertEqual(intake.form_status, IntakeStatus.SUBMITTED)
        self.assertIn(str(self.both.id), required_from_get)
        self.assertNotIn(str(self.standard_only.id), required_from_get)

    def test_telederm_submit_does_not_require_standard_only_consent(self) -> None:
        intake = self._intake_for(ProcessType.TELEDERM)
        PatientIntakeConsent.objects.create(
            intake_form=intake,
            consent_definition=self.both,
            accepted=True,
            accepted_at=timezone.now(),
        )
        submit_patient_intake_form(intake_form_id=intake.id)
        intake.refresh_from_db()
        self.assertEqual(intake.form_status, IntakeStatus.SUBMITTED)

    def test_attaching_question_to_telederm_does_not_remove_it_from_standard(
        self,
    ) -> None:
        from apps.intake.models import AnamnesisQuestionDefinitionProcess

        AnamnesisQuestionDefinitionProcess.objects.get_or_create(
            question_definition=self.question_a,
            process_type=ProcessType.TELEDERM,
        )
        intake = self._intake_for(ProcessType.STANDARD)
        ctx = get_intake_form_context(intake_form_id=intake.id, form_locale="de-DE")
        question_codes = {q["question_code"] for q in ctx["anamnesis_questions"]}
        self.assertIn("PT_Q_A", question_codes)
