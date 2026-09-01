from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.intake.models import (
    AnamnesisQuestionDefinition,
    AnamnesisQuestionDefinitionProcess,
    ConsentDefinition,
    ConsentDefinitionProcess,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.intake.services import (
    get_intake_form_context,
    submit_patient_intake_form,
)
from apps.telederm.services import save_telederm_payload
from apps.telederm.tests.smoke_answers import SMOKE_TELEDERM_ANSWERS
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
from apps.reception.process_types import (
    PROCESS_TYPE_STANDARD,
    PROCESS_TYPE_TELEDERM,
    ProcessType,
)
from apps.reception.services import (
    QUEUE_ENTRY_CANCELLED_MESSAGE_KEY,
    create_queue_entry,
    update_queue_entry,
)
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

    def test_check_constraint_rejects_unknown_process_type(self) -> None:
        with self.assertRaises(IntegrityError):
            QueueEntry.objects.create(
                daily_queue=self.queue,
                patient=self.patient,
                position_no=1,
                created_by_user=self.user,
                process_type="VIDEO",
            )

    def test_uncancel_rejected_when_same_process_active(self) -> None:
        first = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        first.entry_status = QueueEntryStatus.CANCELLED
        first.save(update_fields=["entry_status", "updated_at"])
        create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        with self.assertRaises(DomainError) as ctx:
            update_queue_entry(first.id, entry_status=QueueEntryStatus.WAITING)
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.queue_entry_process_type_exists",
        )
        first.refresh_from_db()
        self.assertEqual(first.entry_status, QueueEntryStatus.CANCELLED)

    def test_uncancel_allowed_when_no_active_same_process(self) -> None:
        first = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        first.entry_status = QueueEntryStatus.CANCELLED
        first.save(update_fields=["entry_status", "updated_at"])
        update_queue_entry(first.id, entry_status=QueueEntryStatus.WAITING)
        first.refresh_from_db()
        self.assertEqual(first.entry_status, QueueEntryStatus.WAITING)


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

    def test_post_invalid_process_type_domain_error_returns_400(self) -> None:
        """Service DomainError must be 400 even if the schema already allowed the body."""
        with patch(
            "apps.reception.api_views_split.queues.create_queue_entry",
            side_effect=DomainError(
                "invalid process type",
                api_message_key="other.domain.invalid_process_type",
                api_message_params={"value": "VIDEO"},
            ),
        ):
            response = self._post(
                {
                    "patient_id": str(self.patient.id),
                    "created_by_user_id": str(self.user.id),
                    "process_type": ProcessType.STANDARD,
                }
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error_key"],
            "other.domain.invalid_process_type",
        )

    def test_post_session_on_cancelled_returns_400(self) -> None:
        entry = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
        )
        entry.entry_status = QueueEntryStatus.CANCELLED
        entry.save(update_fields=["entry_status", "updated_at"])
        response = self.client.post(
            f"/api/v1/queue-entries/{entry.id}/sessions",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error_key"], QUEUE_ENTRY_CANCELLED_MESSAGE_KEY
        )

    def test_patch_uncancel_when_replacement_exists_returns_400(self) -> None:
        first = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
        )
        first.entry_status = QueueEntryStatus.CANCELLED
        first.save(update_fields=["entry_status", "updated_at"])
        create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
        )
        response = self.client.patch(
            f"/api/v1/queue-entries/{first.id}",
            data=json.dumps({"entry_status": "WAITING"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error_key"],
            "other.domain.queue_entry_process_type_exists",
        )
        first.refresh_from_db()
        self.assertEqual(first.entry_status, QueueEntryStatus.CANCELLED)


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

    def test_admin_change_uncancel_rejects_duplicate_process_type(self) -> None:
        first = create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        first.entry_status = QueueEntryStatus.CANCELLED
        first.save(update_fields=["entry_status", "updated_at"])
        create_queue_entry(
            daily_queue_id=self.queue.id,
            patient_id=self.patient.id,
            created_by_user_id=self.user.id,
            process_type=ProcessType.STANDARD,
        )
        first.entry_status = QueueEntryStatus.WAITING
        form = type(
            "BoundQueueEntryForm",
            (),
            {
                "changed_data": ["entry_status"],
                "cleaned_data": {"entry_status": QueueEntryStatus.WAITING},
            },
        )()
        with self.assertRaises(DomainError):
            QueueEntryAdmin(QueueEntry, AdminSite()).save_model(
                _request_with_messages(self.user), first, form, True
            )
        first.refresh_from_db()
        self.assertEqual(first.entry_status, QueueEntryStatus.CANCELLED)


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

    def _fill_smoke_telederm(self, intake: PatientIntakeForm) -> None:
        save_telederm_payload(
            intake_form_id=intake.id,
            form_locale="de-DE",
            payload=SMOKE_TELEDERM_ANSWERS,
        )

    def test_standard_context_includes_standard_catalog_not_telederm_only(
        self,
    ) -> None:
        intake = self._intake_for(PROCESS_TYPE_STANDARD)
        ctx = get_intake_form_context(intake_form_id=intake.id, form_locale="de-DE")
        codes = {c["code"] for c in ctx["consents"]}
        self.assertIn("PT_STANDARD_ONLY", codes)
        self.assertIn("PT_BOTH", codes)
        question_codes = {q["question_code"] for q in ctx["anamnesis_questions"]}
        self.assertIn("PT_Q_A", question_codes)
        self.assertEqual(ctx["process_type"], ProcessType.STANDARD)

    def test_telederm_context_includes_telederm_catalog(self) -> None:
        intake = self._intake_for(PROCESS_TYPE_TELEDERM)
        ctx = get_intake_form_context(intake_form_id=intake.id, form_locale="de-DE")
        self.assertIn("telederm", ctx)
        self.assertIn("questions", ctx["telederm"])
        question_ids = {q["question_id"] for q in ctx["telederm"]["questions"]}
        self.assertIn("T001", question_ids)

    def test_telederm_context_excludes_standard_only_catalog(self) -> None:
        intake = self._intake_for(PROCESS_TYPE_TELEDERM)
        ctx = get_intake_form_context(intake_form_id=intake.id, form_locale="de-DE")
        codes = {c["code"] for c in ctx["consents"]}
        self.assertNotIn("PT_STANDARD_ONLY", codes)
        self.assertIn("PT_BOTH", codes)
        question_codes = {q["question_code"] for q in ctx["anamnesis_questions"]}
        self.assertNotIn("PT_Q_A", question_codes)
        self.assertEqual(ctx["process_type"], ProcessType.TELEDERM)

    def test_get_and_submit_use_the_same_consent_filter(self) -> None:
        intake = self._intake_for(PROCESS_TYPE_TELEDERM)
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
        self._fill_smoke_telederm(intake)
        submit_patient_intake_form(intake_form_id=intake.id)
        intake.refresh_from_db()
        self.assertEqual(intake.form_status, IntakeStatus.SUBMITTED)
        self.assertIn(str(self.both.id), required_from_get)
        self.assertNotIn(str(self.standard_only.id), required_from_get)

    def test_telederm_submit_does_not_require_standard_only_consent(self) -> None:
        intake = self._intake_for(PROCESS_TYPE_TELEDERM)
        PatientIntakeConsent.objects.create(
            intake_form=intake,
            consent_definition=self.both,
            accepted=True,
            accepted_at=timezone.now(),
        )
        self._fill_smoke_telederm(intake)
        submit_patient_intake_form(intake_form_id=intake.id)
        intake.refresh_from_db()
        self.assertEqual(intake.form_status, IntakeStatus.SUBMITTED)

    def test_attaching_question_to_telederm_does_not_remove_it_from_standard(
        self,
    ) -> None:
        AnamnesisQuestionDefinitionProcess.objects.get_or_create(
            question_definition=self.question_a,
            process_type=ProcessType.TELEDERM,
        )
        intake = self._intake_for(PROCESS_TYPE_STANDARD)
        ctx = get_intake_form_context(intake_form_id=intake.id, form_locale="de-DE")
        question_codes = {q["question_code"] for q in ctx["anamnesis_questions"]}
        self.assertIn("PT_Q_A", question_codes)

    def test_check_constraint_rejects_unknown_consent_process_type(self) -> None:
        with self.assertRaises(IntegrityError):
            ConsentDefinitionProcess.objects.create(
                consent_definition=self.both,
                process_type="VIDEO",
            )

    def test_check_constraint_rejects_unknown_question_process_type(self) -> None:
        with self.assertRaises(IntegrityError):
            AnamnesisQuestionDefinitionProcess.objects.create(
                question_definition=self.question_a,
                process_type="VIDEO",
            )


class QueueDuplicateResolutionTests(SimpleTestCase):
    def _row(self, **kwargs):
        from uuid import uuid4

        from apps.reception.queue_duplicate_resolution import QueueDuplicateCandidate

        defaults = {
            "id": uuid4(),
            "entry_status": "WAITING",
            "created_at": timezone.now(),
            "has_submitted_or_reopened_intake": False,
            "has_intake_form": False,
            "has_paper_authorization": False,
            "has_medical_document": False,
            "has_form_session": False,
        }
        defaults.update(kwargs)
        return QueueDuplicateCandidate(**defaults)

    def test_empty_reimport_loses_to_submitted_intake(self) -> None:
        from datetime import timedelta

        from apps.reception.queue_duplicate_resolution import pick_keep_candidate

        older_empty = self._row(created_at=timezone.now() - timedelta(days=30))
        newer_with_form = self._row(
            has_submitted_or_reopened_intake=True,
            has_intake_form=True,
        )
        keep = pick_keep_candidate([older_empty, newer_with_form])
        self.assertEqual(keep.id, newer_with_form.id)

    def test_two_clinical_rows_are_ambiguous(self) -> None:
        from apps.reception.queue_duplicate_resolution import (
            AmbiguousQueueDuplicates,
            pick_keep_candidate,
        )

        digital = self._row(entry_status="PATIENT_COMPLETED")
        paper = self._row(entry_status="PAPER_INTAKE_COMPLETED")
        with self.assertRaises(AmbiguousQueueDuplicates):
            pick_keep_candidate([digital, paper])

    def test_two_empty_waiting_keeps_older(self) -> None:
        from datetime import timedelta

        from apps.reception.queue_duplicate_resolution import pick_keep_candidate

        older = self._row(created_at=timezone.now() - timedelta(days=10))
        newer = self._row(created_at=timezone.now())
        keep = pick_keep_candidate([newer, older])
        self.assertEqual(keep.id, older.id)

    def test_paper_auth_waiting_beats_empty_waiting(self) -> None:
        from apps.reception.queue_duplicate_resolution import pick_keep_candidate

        empty = self._row()
        paper = self._row(has_paper_authorization=True)
        keep = pick_keep_candidate([empty, paper])
        self.assertEqual(keep.id, paper.id)

    def test_patient_completed_beats_waiting(self) -> None:
        from apps.reception.queue_duplicate_resolution import pick_keep_candidate

        waiting = self._row()
        done = self._row(entry_status="PATIENT_COMPLETED")
        keep = pick_keep_candidate([waiting, done])
        self.assertEqual(keep.id, done.id)
