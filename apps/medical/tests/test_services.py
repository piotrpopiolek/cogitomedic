from __future__ import annotations

import inspect
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.exceptions import DomainError, IdempotencyConflictError
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
    PaperIntakeAuthorization,
)
from apps.medical.services import (
    PAPER_INTAKE_AUTOREVOKE_TRIGGER_INTAKE_SUBMITTED,
    PAPER_INTAKE_AUTOREVOKE_TRIGGER_QUEUE_ENTRY_CANCELLED,
    authorize_paper_intake,
    autorevoke_paper_intake_authorization_after_intake_submit,
    create_medical_document_without_intake,
    create_or_get_medical_document,
    get_medical_document_context,
    publish_document_version,
    revoke_document_version,
    revoke_paper_intake_authorization,
    save_draft_document_version,
)
from apps.operations.models import AuditEvent
from apps.operations.services import REF_KEY
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from django.core.exceptions import ObjectDoesNotExist

from apps.core.api_utils import assign_group_to_test_user
from apps.medical.services import (
    check_doctor_document_access,
    check_doctor_queue_entry_access,
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
from apps.reception.services import update_queue_entry
from apps.users.models import StaffUser

_PAPER_AUTH_REASON = (
    "Paper intake path authorized for this queue entry in test (long enough)."
)


class MedicalServicesTests(TestCase):
    def setUp(self) -> None:
        self.doctor_user = StaffUser.objects.create_user(
            username="doctor1",
            email="doctor1@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")

        self.reception_user = StaffUser.objects.create_user(
            username="reception1",
            email="reception1@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.admin_user = StaffUser.objects.create_user(
            username="admin_med",
            email="admin.med@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.manager_user = StaffUser.objects.create_user(
            username="manager_med",
            email="manager.med@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.manager_user, "Manager")
        clinic = ClinicSite.objects.create(code="MUC", name="Munich")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="M1", name="M1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="Med",
            last_name="Patient",
            date_of_birth=date(1981, 1, 1),
            phone="+49888888888",
            email="med.patient@example.com",
            doctolib_patient_id="DOC-M-1",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.reception_user,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        self.queue_entry.active_session = self.session
        self.queue_entry.save(update_fields=["active_session", "updated_at"])
        self.intake_form = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=self.session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/signature.png",
            signature_sha256="c" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"answers": []},
        )
        self.medical_document = create_or_get_medical_document(
            queue_entry_id=self.queue_entry.id,
            intake_form_id=self.intake_form.id,
            created_by_user_id=self.doctor_user.id,
        )

    def test_medical_document_defaults_to_digital_intake(self) -> None:
        self.assertEqual(
            self.medical_document.source_type,
            MedicalDocumentSourceType.DIGITAL_INTAKE,
        )

    def test_get_medical_document_context_includes_stripped_reception_note(
        self,
    ) -> None:
        self.intake_form.reception_note = "  Bitte Geburtsdatum prüfen  "
        self.intake_form.save(update_fields=["reception_note", "updated_at"])
        ctx = get_medical_document_context(
            medical_document_id=self.medical_document.id,
            form_locale="de-DE",
            user=self.doctor_user,
        )
        self.assertEqual(
            ctx["intake_summary"]["reception_note"],
            "Bitte Geburtsdatum prüfen",
        )

    def test_get_medical_document_context_uses_telederm_preview(self) -> None:
        from apps.reception.process_types import PROCESS_TYPE_TELEDERM

        self.queue_entry.process_type = PROCESS_TYPE_TELEDERM
        self.queue_entry.save(update_fields=["process_type", "updated_at"])
        preview = {
            "schema_version": 1,
            "triage_blocked": False,
            "path_code": "CCE-001",
            "problem_label": "Neue Hautveränderung",
            "lines": [],
        }
        with patch(
            "apps.medical.services.get_intake_form_context",
            return_value={
                "consents": [],
                "body_map_data": [],
                "anamnesis_questions": [],
                "patient": {"id": str(self.queue_entry.patient_id)},
                "telederm": {"clinical_summary_preview": preview},
            },
        ):
            ctx = get_medical_document_context(
                medical_document_id=self.medical_document.id,
                form_locale="de-DE",
                user=self.doctor_user,
            )
        self.assertEqual(ctx["intake_summary"]["clinical_summary"], preview)

    def test_get_medical_document_context_builds_telederm_summary_fallback(
        self,
    ) -> None:
        from apps.reception.process_types import PROCESS_TYPE_TELEDERM

        self.queue_entry.process_type = PROCESS_TYPE_TELEDERM
        self.queue_entry.save(update_fields=["process_type", "updated_at"])
        self.intake_form.telederm_payload = {
            "schema_version": 1,
            "answers": {
                "T001": {"selected": ["NONE"]},
                "CC001": {"selected": ["NEW_SKIN_LESION"]},
            },
        }
        self.intake_form.save(update_fields=["telederm_payload", "updated_at"])
        with patch(
            "apps.medical.services.get_intake_form_context",
            return_value={
                "consents": [],
                "body_map_data": [],
                "anamnesis_questions": [],
                "patient": {"id": str(self.queue_entry.patient_id)},
                "telederm": {"questions": []},
            },
        ):
            ctx = get_medical_document_context(
                medical_document_id=self.medical_document.id,
                form_locale="de-DE",
                user=self.doctor_user,
            )
        self.assertIn("clinical_summary", ctx["intake_summary"])
        self.assertIn("problem_label", ctx["intake_summary"]["clinical_summary"])

    def test_medical_document_consistency_constraint_blocks_paper_with_intake(
        self,
    ) -> None:
        other_patient = Patient.objects.create(
            first_name="Other",
            last_name="Patient",
            date_of_birth=date(1988, 4, 4),
            phone="+48700111222",
            email="other.patient@example.com",
        )
        other_queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=2,
            created_by_user=self.reception_user,
        )
        other_session = PatientFormSession.objects.create(
            queue_entry=other_queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        other_intake_form = PatientIntakeForm.objects.create(
            queue_entry=other_queue_entry,
            session=other_session,
            form_status=IntakeStatus.SUBMITTED,
            signature_sha256="d" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"answers": []},
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MedicalDocument.objects.create(
                    queue_entry=other_queue_entry,
                    intake_form=other_intake_form,
                    source_type=MedicalDocumentSourceType.PAPER_INTAKE,
                    created_by_user=self.doctor_user,
                )

    def test_medical_document_consistency_constraint_blocks_digital_without_intake(
        self,
    ) -> None:
        other_patient = Patient.objects.create(
            first_name="Queue",
            last_name="NoIntake",
            date_of_birth=date(1989, 5, 5),
            phone="+48700111333",
            email="queue.nointake@example.com",
        )
        other_queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=3,
            created_by_user=self.reception_user,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MedicalDocument.objects.create(
                    queue_entry=other_queue_entry,
                    intake_form=None,
                    source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
                    created_by_user=self.doctor_user,
                )

    def test_create_medical_document_without_intake_happy_path(self) -> None:
        patient = Patient.objects.create(
            first_name="Paper",
            last_name="Candidate",
            date_of_birth=date(1980, 6, 6),
            phone="+48700222444",
            email="paper.candidate@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=5,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )

        authorize_paper_intake(
            queue_entry_id=queue_entry.id,
            authorized_by_user_id=self.admin_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        doc = create_medical_document_without_intake(
            queue_entry_id=queue_entry.id,
            created_by_user_id=self.doctor_user.id,
        )

        queue_entry.refresh_from_db()
        self.assertEqual(doc.queue_entry_id, queue_entry.id)
        self.assertIsNone(doc.intake_form_id)
        self.assertEqual(doc.source_type, MedicalDocumentSourceType.PAPER_INTAKE)
        self.assertEqual(
            queue_entry.entry_status, QueueEntryStatus.PAPER_INTAKE_COMPLETED
        )
        self.assertIsNotNone(queue_entry.doctor_list_sort_at)
        ctx = get_medical_document_context(
            medical_document_id=doc.id,
            form_locale="de-DE",
            user=self.doctor_user,
        )
        self.assertEqual(ctx["source_type"], MedicalDocumentSourceType.PAPER_INTAKE)
        paper = ctx["paper_intake_authorization"]
        self.assertIsNotNone(paper)
        self.assertEqual(paper["reason"], _PAPER_AUTH_REASON)
        self.assertEqual(paper["authorized_by_user_id"], str(self.admin_user.id))
        p = ctx["intake_summary"]["patient"]
        self.assertEqual(ctx["intake_summary"]["reception_note"], "")
        self.assertEqual(
            set(p.keys()),
            {"id", "first_name", "last_name", "date_of_birth", "phone", "email"},
        )
        self.assertEqual(p["id"], str(patient.id))
        self.assertEqual(p["first_name"], patient.first_name)
        self.assertEqual(p["last_name"], patient.last_name)
        self.assertEqual(p["date_of_birth"], patient.date_of_birth.isoformat())
        self.assertEqual(p["phone"], patient.phone)
        self.assertEqual(p["email"], patient.email)

    def test_get_medical_document_context_paper_intake_patient_allows_null_dob(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="No",
            last_name="Dob",
            date_of_birth=None,
            phone="+48700555666",
            email="no.dob@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=51,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        authorize_paper_intake(
            queue_entry_id=queue_entry.id,
            authorized_by_user_id=self.manager_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        doc = create_medical_document_without_intake(
            queue_entry_id=queue_entry.id,
            created_by_user_id=self.doctor_user.id,
        )
        ctx = get_medical_document_context(
            medical_document_id=doc.id,
            form_locale="de-DE",
            user=self.doctor_user,
        )
        self.assertIsNone(ctx["intake_summary"]["patient"]["date_of_birth"])

    def test_get_medical_document_context_paper_intake_missing_audit_raises(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="No",
            last_name="AuditSnap",
            date_of_birth=date(1979, 7, 7),
            phone="+48700666777",
            email="no.audit.snap@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=52,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        authorize_paper_intake(
            queue_entry_id=queue_entry.id,
            authorized_by_user_id=self.admin_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        doc = create_medical_document_without_intake(
            queue_entry_id=queue_entry.id,
            created_by_user_id=self.doctor_user.id,
        )
        AuditEvent.objects.filter(
            medical_document_id=doc.id,
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
        ).delete()
        with self.assertRaises(DomainError) as ctx:
            get_medical_document_context(
                medical_document_id=doc.id,
                form_locale="de-DE",
                user=self.doctor_user,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_document_audit_snapshot_missing",
        )

    def test_revoke_paper_intake_authorization_unknown_staff_raises_domain_error(
        self,
    ) -> None:
        with self.assertRaises(DomainError) as ctx:
            revoke_paper_intake_authorization(
                queue_entry_id=self.queue_entry.id,
                revoked_by_user_id=uuid4(),
                reason="administrator revoke audit trail text here",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.api.staff_user_not_found",
        )

    def test_revoke_paper_intake_authorization_queue_entry_not_found(
        self,
    ) -> None:
        with self.assertRaises(DomainError) as ctx:
            revoke_paper_intake_authorization(
                queue_entry_id=uuid4(),
                revoked_by_user_id=self.admin_user.id,
                reason="administrator revoke audit trail text here",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.api.queue_entry_not_found",
        )

    def test_create_medical_document_without_intake_requires_waiting_status(
        self,
    ) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.queue_entry.id,
                created_by_user_id=self.doctor_user.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.queue_entry_must_be_waiting_for_paper_intake",
        )

    def test_create_medical_document_without_intake_requires_appointment_time(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="No",
            last_name="Appointment",
            date_of_birth=date(1979, 7, 7),
            phone="+48700333555",
            email="no.appointment@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=6,
            appointment_time=None,
            created_by_user=self.reception_user,
        )
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=queue_entry.id,
                created_by_user_id=self.doctor_user.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_requires_appointment_time",
        )

    def test_create_medical_document_without_intake_enforces_three_hour_window(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="Too",
            last_name="Early",
            date_of_birth=date(1978, 8, 8),
            phone="+48700444666",
            email="too.early@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=7,
            appointment_time=timezone.now() - timedelta(hours=2, minutes=59),
            created_by_user=self.reception_user,
        )
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=queue_entry.id,
                created_by_user_id=self.doctor_user.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_earliest_after_appointment",
        )

    def test_create_medical_document_without_intake_rejects_existing_document(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="Existing",
            last_name="Document",
            date_of_birth=date(1977, 9, 9),
            phone="+48700555777",
            email="existing.document@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=8,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.reception_user,
        )
        intake_form = PatientIntakeForm.objects.create(
            queue_entry=queue_entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_sha256="e" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"answers": []},
        )
        MedicalDocument.objects.create(
            queue_entry=queue_entry,
            intake_form=intake_form,
            source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            created_by_user=self.doctor_user,
            updated_by_user=self.doctor_user,
        )
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=queue_entry.id,
                created_by_user_id=self.doctor_user.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.medical_document_already_exists_for_queue_entry",
        )

    def test_create_medical_document_without_intake_rejects_without_authorization(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="No",
            last_name="Auth",
            date_of_birth=date(1982, 2, 2),
            phone="+48700111222",
            email="no.auth@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=52,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=queue_entry.id,
                created_by_user_id=self.doctor_user.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_not_authorized",
        )

    def test_create_medical_document_without_intake_signature_has_no_reason_param(
        self,
    ) -> None:
        sig = inspect.signature(create_medical_document_without_intake)
        self.assertNotIn("reason", sig.parameters)

    def test_authorize_paper_intake_sets_sort_at_and_audit(self) -> None:
        patient = Patient.objects.create(
            first_name="Auth",
            last_name="Paper",
            date_of_birth=date(1983, 3, 3),
            phone="+48700222333",
            email="auth.paper@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=53,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        auth = authorize_paper_intake(
            queue_entry_id=queue_entry.id,
            authorized_by_user_id=self.manager_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        queue_entry.refresh_from_db()
        self.assertEqual(auth.queue_entry_id, queue_entry.id)
        self.assertEqual(queue_entry.entry_status, QueueEntryStatus.WAITING)
        self.assertIsNotNone(queue_entry.doctor_list_sort_at)
        ev = AuditEvent.objects.filter(event_type="PAPER_INTAKE_AUTHORIZED").first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.metadata.get("authorization_id"), str(auth.id))

    def test_authorize_paper_intake_rejects_doctor_role(self) -> None:
        patient = Patient.objects.create(
            first_name="Doc",
            last_name="TryAuth",
            date_of_birth=date(1984, 4, 4),
            phone="+48700333444",
            email="doc.try@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=54,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=queue_entry.id,
                authorized_by_user_id=self.doctor_user.id,
                reason=_PAPER_AUTH_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_authorization_invalid_role",
        )

    def test_revoke_paper_intake_clears_doctor_list_sort_at(self) -> None:
        patient = Patient.objects.create(
            first_name="Rev",
            last_name="Sort",
            date_of_birth=date(1985, 5, 5),
            phone="+48700444555",
            email="rev.sort@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=55,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        authorize_paper_intake(
            queue_entry_id=queue_entry.id,
            authorized_by_user_id=self.admin_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        queue_entry.refresh_from_db()
        self.assertIsNotNone(queue_entry.doctor_list_sort_at)
        revoke_paper_intake_authorization(
            queue_entry_id=queue_entry.id,
            revoked_by_user_id=self.admin_user.id,
            reason="Administrative revoke with audit text long enough.",
        )
        queue_entry.refresh_from_db()
        self.assertIsNone(queue_entry.doctor_list_sort_at)
        self.assertFalse(
            PaperIntakeAuthorization.objects.filter(
                queue_entry_id=queue_entry.id
            ).exists()
        )

    def test_autorevoke_paper_intake_after_intake_submit_removes_authorization(
        self,
    ) -> None:
        patient = Patient.objects.create(
            first_name="Auto",
            last_name="Revoke",
            date_of_birth=date(1984, 4, 4),
            phone="+48700666777",
            email="auto.revoke@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=57,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.reception_user,
        )
        intake_form = PatientIntakeForm.objects.create(
            queue_entry=queue_entry,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
            anamnesis_payload={"schema_version": 1, "answers": []},
        )
        authorize_paper_intake(
            queue_entry_id=queue_entry.id,
            authorized_by_user_id=self.admin_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        self.assertTrue(
            PaperIntakeAuthorization.objects.filter(
                queue_entry_id=queue_entry.id
            ).exists()
        )

        autorevoke_paper_intake_authorization_after_intake_submit(
            queue_entry_id=queue_entry.id,
            intake_form_id=intake_form.id,
            actor_user_id=self.doctor_user.id,
        )

        self.assertFalse(
            PaperIntakeAuthorization.objects.filter(
                queue_entry_id=queue_entry.id
            ).exists()
        )
        ev = (
            AuditEvent.objects.filter(
                event_type="PAPER_INTAKE_AUTHORIZATION_AUTOREVOKED",
                patient_id=patient.id,
            )
            .order_by("-event_time")
            .first()
        )
        self.assertIsNotNone(ev)
        self.assertEqual(
            ev.metadata.get("trigger"),
            PAPER_INTAKE_AUTOREVOKE_TRIGGER_INTAKE_SUBMITTED,
        )
        self.assertEqual(ev.metadata.get("intake_form_id"), str(intake_form.id))

    def test_update_queue_entry_cancel_autorevokes_paper_authorization(self) -> None:
        patient = Patient.objects.create(
            first_name="Cancel",
            last_name="Paper",
            date_of_birth=date(1986, 6, 6),
            phone="+48700555666",
            email="cancel.paper@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=56,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception_user,
        )
        authorize_paper_intake(
            queue_entry_id=queue_entry.id,
            authorized_by_user_id=self.admin_user.id,
            reason=_PAPER_AUTH_REASON,
        )
        update_queue_entry(
            queue_entry.id,
            entry_status=QueueEntryStatus.CANCELLED,
            actor_user_id=self.admin_user.id,
        )
        self.assertFalse(
            PaperIntakeAuthorization.objects.filter(
                queue_entry_id=queue_entry.id
            ).exists()
        )
        cancel_ev = (
            AuditEvent.objects.filter(
                event_type="PAPER_INTAKE_AUTHORIZATION_AUTOREVOKED",
                patient_id=patient.id,
            )
            .order_by("-event_time")
            .first()
        )
        self.assertIsNotNone(cancel_ev)
        self.assertEqual(cancel_ev.actor_user_id, self.admin_user.id)
        self.assertEqual(
            cancel_ev.metadata.get("trigger"),
            PAPER_INTAKE_AUTOREVOKE_TRIGGER_QUEUE_ENTRY_CANCELLED,
        )

    def test_save_draft_document_version_creates_new_version(self) -> None:
        version = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "lesions": []},
            diagnosis_code="D1",
            procedure_code="P1",
        )
        self.medical_document.refresh_from_db()

        self.assertEqual(version.version_no, 1)
        self.assertEqual(version.version_status, DocVersionStatus.DRAFT)
        self.assertEqual(self.medical_document.current_version_no, 1)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.DRAFT)
        audit = AuditEvent.objects.filter(
            event_type="DOCUMENT_DRAFT_SAVED",
            medical_document_id=self.medical_document.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(
            audit.context_clinic_site_id, self.queue_entry.daily_queue.clinic_site_id
        )
        ref = audit.metadata.get(REF_KEY) or {}
        self.assertEqual(
            ref.get("patient_id"), str(self.medical_document.queue_entry.patient_id)
        )
        self.assertEqual(ref.get("medical_document_id"), str(self.medical_document.id))
        self.assertEqual(
            ref.get("context_clinic_site_id"),
            str(self.queue_entry.daily_queue.clinic_site_id),
        )

    def test_save_draft_document_version_updates_existing_draft(self) -> None:
        first = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "value": 1},
        )
        second = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "value": 2},
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.medical_payload["value"], 2)
        self.assertEqual(
            self.medical_document.versions.count(),
            1,
        )

    def test_publish_document_version_sets_published_and_enqueues_outbox(self) -> None:
        draft = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        request_id = uuid4()

        published = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=request_id,
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        self.medical_document.refresh_from_db()

        self.assertEqual(published.id, draft.id)
        self.assertEqual(published.version_status, DocVersionStatus.PUBLISHED)
        self.assertEqual(published.publish_request_id, request_id)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertTrue(
            OutboxEvent.objects.filter(
                medical_document_version=published,
                event_type=OutboxEventType.GENERATE_PDF,
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="DOCUMENT_PUBLISHED",
                medical_document_id=self.medical_document.id,
            ).exists()
        )

    def test_publish_document_version_rejects_non_doctor_publisher(self) -> None:
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        with self.assertRaises(DomainError) as ctx:
            publish_document_version(
                medical_document_id=self.medical_document.id,
                publish_request_id=uuid4(),
                published_by_user_id=self.manager_user.id,
                publish_locale="de-DE",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.medical_document_publish_doctor_role_required",
        )

    def test_publish_document_version_is_idempotent_for_same_request_id(self) -> None:
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        request_id = uuid4()
        first = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=request_id,
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        second = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=request_id,
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(
            OutboxEvent.objects.filter(
                medical_document_version=first, event_type=OutboxEventType.GENERATE_PDF
            ).count(),
            1,
        )

    def test_publish_document_version_same_request_id_conflicting_locale_raises(
        self,
    ) -> None:
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        request_id = uuid4()
        published = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=request_id,
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        self.assertEqual(
            OutboxEvent.objects.filter(
                medical_document_version=published,
                event_type=OutboxEventType.GENERATE_PDF,
            ).count(),
            1,
        )
        with self.assertRaises(IdempotencyConflictError) as ctx:
            publish_document_version(
                medical_document_id=self.medical_document.id,
                publish_request_id=request_id,
                published_by_user_id=self.doctor_user.id,
                publish_locale="en-GB",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.api.publish_request_id_locale_conflict",
        )
        self.assertEqual(
            OutboxEvent.objects.filter(
                medical_document_version=published,
                event_type=OutboxEventType.GENERATE_PDF,
            ).count(),
            1,
        )

    def test_publish_document_version_returns_in_progress_publication(self) -> None:
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
            },
        )
        first = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        second = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(self.medical_document.versions.count(), 1)

    def test_check_doctor_document_access_allows_author(self) -> None:
        # doctor_user is the author of self.medical_document
        # Should not raise exception
        check_doctor_document_access(self.medical_document, self.doctor_user)

    def test_check_doctor_document_access_allows_assigned_doctor_only_for_shared_work(
        self,
    ) -> None:
        other_doctor = StaffUser.objects.create_user(
            username="otherdoc",
            email="otherdoc@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(other_doctor, "Doctor")

        # DRAFT: any doctor may access (shared queue)
        check_doctor_document_access(self.medical_document, other_doctor)

        MedicalDocument.objects.filter(pk=self.medical_document.id).update(
            status=MedicalDocStatus.PUBLISHED
        )
        self.medical_document.refresh_from_db()
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_document_access(self.medical_document, other_doctor)

        # Assigned doctor does not bypass publisher-only rule on published docs
        self.medical_document.queue_entry.daily_queue.assigned_doctor = other_doctor
        self.medical_document.queue_entry.daily_queue.save()
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_document_access(self.medical_document, other_doctor)

    def test_check_doctor_document_access_allows_admin(self) -> None:
        admin_user = StaffUser.objects.create_user(
            username="adminuser",
            email="admin@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(admin_user, "Admin")

        # Admin can access any document
        check_doctor_document_access(self.medical_document, admin_user)

    def test_check_doctor_queue_entry_access(self) -> None:
        # Creator can open without assigned_doctor while document is DRAFT
        check_doctor_queue_entry_access(self.queue_entry, self.doctor_user)

        other_doctor = StaffUser.objects.create_user(
            username="qe_other",
            email="qe_other@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(other_doctor, "Doctor")
        check_doctor_queue_entry_access(self.queue_entry, other_doctor)

        MedicalDocument.objects.filter(pk=self.medical_document.id).update(
            status=MedicalDocStatus.PUBLISHED
        )
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_queue_entry_access(self.queue_entry, other_doctor)

        self.queue_entry.daily_queue.assigned_doctor = other_doctor
        self.queue_entry.daily_queue.save()
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_queue_entry_access(self.queue_entry, other_doctor)

    def test_check_doctor_queue_entry_access_doctor_without_medical_document(
        self,
    ) -> None:
        other_doctor = StaffUser.objects.create_user(
            username="qe_no_doc",
            email="qe_no_doc@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(other_doctor, "Doctor")
        patient2 = Patient.objects.create(
            first_name="No",
            last_name="DocYet",
            date_of_birth=date(1982, 2, 2),
            phone="+49999999999",
            email="nodoc@example.com",
            doctolib_patient_id="DOC-NO-M",
        )
        entry2 = QueueEntry.objects.create(
            daily_queue=self.queue_entry.daily_queue,
            patient=patient2,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=2,
            created_by_user=self.reception_user,
        )
        check_doctor_queue_entry_access(entry2, other_doctor)
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_queue_entry_access(entry2, self.reception_user)

    def test_check_doctor_queue_entry_access_rejects_cancelled(self) -> None:
        self.queue_entry.entry_status = QueueEntryStatus.CANCELLED
        self.queue_entry.save(update_fields=["entry_status", "updated_at"])
        with self.assertRaises(ObjectDoesNotExist):
            check_doctor_queue_entry_access(self.queue_entry, self.doctor_user)


class LesionGroupFavoritesAdminTests(TestCase):
    """Tests for lesion_group_favorites widget and form validation in admin."""

    def test_widget_render_contains_textarea_and_visual_editor_markup(self) -> None:
        from apps.medical.widgets import LesionGroupFavoritesWidget

        w = LesionGroupFavoritesWidget()
        html = w.render(
            "lesion_group_favorites", [], {"id": "id_lesion_group_favorites"}
        )
        self.assertIn('name="lesion_group_favorites"', html)
        self.assertIn("id_lesion_group_favorites", html)
        self.assertIn("lesionGroupFavoritesWidget", html)
        self.assertIn("lesion-group-favorites-", html)
        self.assertIn('x-data="lesionGroupFavoritesWidget', html)
        self.assertIn("border-base-200", html)

    def test_widget_render_includes_choices_data(self) -> None:
        import base64
        import json

        from apps.medical.widgets import LesionGroupFavoritesWidget

        w = LesionGroupFavoritesWidget()
        html = w.render("lesion_group_favorites", [], {"id": "id_lgf"})
        ctx = w.get_context("lesion_group_favorites", [], {"id": "id_lgf"})
        wgt = ctx["widget"]
        for key in ("dermatoscopic_b64", "clinical_b64", "malignancy_b64"):
            blob = wgt[key]
            self.assertIn(blob, html, msg=f"expected {key} payload in rendered HTML")
        derm = json.loads(base64.b64decode(wgt["dermatoscopic_b64"]))
        clinical = json.loads(base64.b64decode(wgt["clinical_b64"]))
        malignancy = json.loads(base64.b64decode(wgt["malignancy_b64"]))
        self.assertTrue(any(x["value"] == "ASYMMETRY" for x in derm))
        self.assertTrue(any(x["value"] == "CONTROL_NEEDED" for x in clinical))
        self.assertTrue(any(x["value"] == "NO_SUSPICION" for x in malignancy))

    def test_form_clean_lesion_group_favorites_valid_list_passes(self) -> None:
        from apps.medical.admin import DoctorTextTemplateForm

        form = DoctorTextTemplateForm(
            data={
                "name": "Test",
                "template_locale": "pl-PL",
                "template_body": "Body",
                "is_global": True,
                "is_active": True,
                "lesion_group_favorites": '[{"name":"P1","dermatoscopic_features":["ASYMMETRY"],"clinical_assessment":"CONTROL_NEEDED","malignancy_risk":"LOW_SUSPICION","text":"Text."}]',
            },
        )
        form.is_valid()
        self.assertNotIn("lesion_group_favorites", form.errors)

    def test_form_clean_lesion_group_favorites_invalid_code_raises(self) -> None:
        from apps.medical.admin import DoctorTextTemplateForm

        form = DoctorTextTemplateForm(
            data={
                "name": "Test",
                "template_locale": "pl-PL",
                "template_body": "Body",
                "lesion_group_favorites": '[{"name":"P1","dermatoscopic_features":["INVALID_CODE"],"clinical_assessment":"CONTROL_NEEDED","malignancy_risk":"LOW_SUSPICION","text":"Text."}]',
            },
        )
        form.is_valid()
        self.assertIn("lesion_group_favorites", form.errors)

    def test_form_clean_lesion_group_favorites_empty_name_raises(self) -> None:
        from apps.medical.admin import DoctorTextTemplateForm

        form = DoctorTextTemplateForm(
            data={
                "name": "Test",
                "template_locale": "pl-PL",
                "template_body": "Body",
                "lesion_group_favorites": '[{"name":"","dermatoscopic_features":[],"clinical_assessment":"UNREMARKABLE","malignancy_risk":"NO_SUSPICION","text":"Some text."}]',
            },
        )
        form.is_valid()
        self.assertIn("lesion_group_favorites", form.errors)


class DocumentRevisionStateTests(MedicalServicesTests):

    def _publish_initial_version(self):
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                "version": 1,
            },
        )
        published = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        OutboxEvent.objects.filter(medical_document_version=published).update(
            status=OutboxStatus.PROCESSED
        )
        self.medical_document.refresh_from_db()
        return published

    def test_save_draft_invalid_intent_raises_distinct_key(self) -> None:
        from apps.core.exceptions import DomainError

        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "lesions": []},
        )
        with self.assertRaises(DomainError) as ctx:
            save_draft_document_version(
                medical_document_id=self.medical_document.id,
                updated_by_user_id=self.doctor_user.id,
                medical_payload={"authoring_locale": "de-DE", "lesions": [], "x": 1},
                intent="typo",
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.invalid_save_draft_intent"
        )

    def test_save_draft_on_published_without_amend_intent_raises(self) -> None:
        from apps.core.exceptions import DomainError

        self._publish_initial_version()

        with self.assertRaises(DomainError) as ctx:
            save_draft_document_version(
                medical_document_id=self.medical_document.id,
                updated_by_user_id=self.doctor_user.id,
                medical_payload={"authoring_locale": "de-DE", "version": 2},
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.amend_intent_required"
        )

        self.medical_document.refresh_from_db()
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertFalse(self.medical_document.has_pending_revision)

    def test_save_draft_on_published_amend_without_edit_session_raises(self) -> None:
        from apps.core.exceptions import DomainError

        self._publish_initial_version()

        with self.assertRaises(DomainError) as ctx:
            save_draft_document_version(
                medical_document_id=self.medical_document.id,
                updated_by_user_id=self.doctor_user.id,
                medical_payload={"authoring_locale": "de-DE", "version": 2},
                intent="amend",
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.amend_requires_edit_session"
        )

        self.medical_document.refresh_from_db()
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertFalse(self.medical_document.has_pending_revision)

    def test_save_draft_amend_keeps_status_published_and_flags_pending(self) -> None:
        from apps.medical.services import begin_pending_revision_from_published

        published = self._publish_initial_version()
        self.assertEqual(self.medical_document.published_version_no, 1)
        self.assertFalse(self.medical_document.has_pending_revision)

        begin_pending_revision_from_published(
            medical_document=self.medical_document,
            actor_user_id=self.doctor_user.id,
        )
        revision = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "version": 2},
            intent="amend",
        )
        self.medical_document.refresh_from_db()

        self.assertEqual(revision.version_no, 2)
        self.assertEqual(revision.version_status, DocVersionStatus.DRAFT)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertEqual(self.medical_document.published_version_no, 1)
        self.assertEqual(self.medical_document.current_version_no, 1)
        self.assertTrue(self.medical_document.has_pending_revision)
        self.assertNotEqual(revision.id, published.id)

        revision_started = AuditEvent.objects.filter(
            event_type="DOCUMENT_REVISION_STARTED",
            medical_document_id=self.medical_document.id,
        ).first()
        self.assertIsNotNone(revision_started)

    def test_context_during_pending_revision_includes_reception_note(self) -> None:
        from apps.medical.services import begin_pending_revision_from_published

        note = "Patient besorgt wegen Stellen auf der Kopfhaut."
        self.intake_form.reception_note = note
        self.intake_form.save(update_fields=["reception_note", "updated_at"])
        self._publish_initial_version()
        begin_pending_revision_from_published(
            medical_document=self.medical_document,
            actor_user_id=self.doctor_user.id,
        )
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "version": 2},
            intent="amend",
        )
        self.medical_document.refresh_from_db()
        self.assertTrue(self.medical_document.has_pending_revision)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)

        ctx = get_medical_document_context(
            medical_document_id=self.medical_document.id,
            form_locale="de-DE",
            user=self.doctor_user,
        )
        self.assertTrue(ctx["has_pending_revision"])
        self.assertEqual(ctx["status"], MedicalDocStatus.PUBLISHED)
        self.assertEqual(ctx["intake_summary"]["reception_note"], note)

    def test_save_draft_amend_updates_existing_pending_revision_in_place(self) -> None:
        from apps.medical.services import begin_pending_revision_from_published

        self._publish_initial_version()
        begin_pending_revision_from_published(
            medical_document=self.medical_document,
            actor_user_id=self.doctor_user.id,
        )
        first = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "rev": 1},
            intent="amend",
        )
        second = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "rev": 2},
            intent="amend",
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.medical_payload["rev"], 2)
        self.assertEqual(self.medical_document.versions.count(), 2)

    def test_discard_pending_revision_removes_draft_and_clears_flag(self) -> None:
        from apps.medical.services import (
            begin_pending_revision_from_published,
            discard_pending_revision,
        )

        self._publish_initial_version()
        begin_pending_revision_from_published(
            medical_document=self.medical_document,
            actor_user_id=self.doctor_user.id,
        )
        revision = save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={"authoring_locale": "de-DE", "rev": 1},
            intent="amend",
        )

        discard_pending_revision(
            medical_document_id=self.medical_document.id,
            actor_user_id=self.doctor_user.id,
        )
        self.medical_document.refresh_from_db()

        self.assertFalse(self.medical_document.has_pending_revision)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertEqual(self.medical_document.current_version_no, 1)
        self.assertFalse(self.medical_document.versions.filter(pk=revision.id).exists())

        discarded = AuditEvent.objects.filter(
            event_type="DOCUMENT_REVISION_DISCARDED",
            medical_document_id=self.medical_document.id,
        ).first()
        self.assertIsNotNone(discarded)

    def test_discard_pending_revision_without_pending_raises(self) -> None:
        from apps.core.exceptions import DomainError
        from apps.medical.services import discard_pending_revision

        self._publish_initial_version()

        with self.assertRaises(DomainError) as ctx:
            discard_pending_revision(
                medical_document_id=self.medical_document.id,
                actor_user_id=self.doctor_user.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.api.no_pending_revision_to_discard",
        )

    def test_publish_after_amend_emits_republished_audit_and_updates_state(
        self,
    ) -> None:
        from apps.medical.services import begin_pending_revision_from_published

        self._publish_initial_version()
        begin_pending_revision_from_published(
            medical_document=self.medical_document,
            actor_user_id=self.doctor_user.id,
        )
        save_draft_document_version(
            medical_document_id=self.medical_document.id,
            updated_by_user_id=self.doctor_user.id,
            medical_payload={
                "schema_version": 1,
                "authoring_locale": "de-DE",
                "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
                "fitzpatrick_type": "TYPE_III",
                "overall_image_assessment": "NO_CONTROL_NEEDED",
                "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
                "final_assessment": "NO_HIGH_GRADE_SUSPICION",
                "rev": 1,
            },
            intent="amend",
        )

        republished = publish_document_version(
            medical_document_id=self.medical_document.id,
            publish_request_id=uuid4(),
            published_by_user_id=self.doctor_user.id,
            publish_locale="de-DE",
        )
        self.medical_document.refresh_from_db()

        self.assertEqual(republished.version_no, 2)
        self.assertEqual(republished.version_status, DocVersionStatus.PUBLISHED)
        self.assertEqual(self.medical_document.published_version_no, 2)
        self.assertEqual(self.medical_document.current_version_no, 2)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertFalse(self.medical_document.has_pending_revision)

        republished_audit = AuditEvent.objects.filter(
            event_type="DOCUMENT_REPUBLISHED",
            medical_document_id=self.medical_document.id,
        ).first()
        self.assertIsNotNone(republished_audit)
        self.assertEqual(republished_audit.metadata.get("new_published_version_no"), 2)
        self.assertEqual(
            republished_audit.metadata.get("previous_published_version_no"), 1
        )

    @patch("apps.medical.services._try_delete_file")
    def test_revoke_document_version_after_full_delivery(
        self, mock_delete_file: MagicMock
    ) -> None:
        published = self._publish_initial_version()
        now = timezone.now()
        MedicalDocumentVersion.objects.filter(id=published.id).update(
            hidrive_sent=True,
            hidrive_sent_at=now,
            sms_sent=True,
            sms_sent_at=now,
            pdf_local_path="/media/befund/test.pdf",
        )
        published.refresh_from_db()

        revoked = revoke_document_version(
            medical_document_id=self.medical_document.id,
            revoked_by_user_id=self.doctor_user.id,
        )

        self.medical_document.refresh_from_db()
        revoked.refresh_from_db()
        self.assertIsNotNone(revoked.revoked_at)
        self.assertIsNone(revoked.pdf_local_path)
        self.assertIsNotNone(revoked.local_pdf_deleted_at)
        self.assertEqual(self.medical_document.status, MedicalDocStatus.PUBLISHED)
        self.assertEqual(self.medical_document.current_version_no, 1)
        self.assertEqual(self.medical_document.published_version_no, 1)
        self.assertFalse(self.medical_document.has_pending_revision)
        mock_delete_file.assert_called_once_with("/media/befund/test.pdf")
        self.assertTrue(
            AuditEvent.objects.filter(event_type="DOCUMENT_REVOKED").exists()
        )

    def test_revoke_document_version_without_hidrive_raises_domain_error(
        self,
    ) -> None:
        published = self._publish_initial_version()
        MedicalDocumentVersion.objects.filter(id=published.id).update(
            hidrive_sent=False,
            hidrive_sent_at=None,
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )
        with self.assertRaises(DomainError) as ctx:
            revoke_document_version(
                medical_document_id=self.medical_document.id,
                revoked_by_user_id=self.doctor_user.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.revoke_requires_full_delivery",
        )
