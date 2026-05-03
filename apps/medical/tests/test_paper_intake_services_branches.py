"""Branch coverage for paper-intake medical services (diff-cover / CI gate)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    PaperIntakeAuthorization,
)
from apps.medical.services import (
    authorize_paper_intake,
    create_medical_document_without_intake,
    revoke_paper_intake_authorization,
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
from apps.users.models import StaffUser

_REASON = "Paper intake authorization reason long enough for validation in tests."


class PaperIntakeAuthorizeBranchesTests(TestCase):
    def setUp(self) -> None:
        self.admin = StaffUser.objects.create_user(
            username="pi-admin",
            email="pi.admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.doctor = StaffUser.objects.create_user(
            username="pi-doctor",
            email="pi.doctor@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.rec = StaffUser.objects.create_user(
            username="pi-rec",
            email="pi.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.rec, "Reception")
        clinic = ClinicSite.objects.create(code="PI", name="Paper Intake Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.rec,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="P",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="+48111222333",
            email="pi.patient@example.com",
        )
        self.waiting = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.rec,
        )

    def test_authorize_rejects_doctor_role(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.doctor.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_authorization_invalid_role",
        )

    def test_authorize_reason_too_short(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.admin.id,
                reason="short",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.api.paper_intake_authorization_reason_required",
        )

    def test_authorize_reason_too_long(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.admin.id,
                reason="x" * 600,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.api.paper_intake_authorization_reason_too_long",
        )

    def test_authorize_unknown_queue_entry(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=uuid.uuid4(),
                authorized_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.queue_entry_not_found"
        )

    def test_authorize_unknown_staff_user(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=uuid.uuid4(),
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.staff_user_not_found"
        )

    def test_authorize_invalid_entry_status(self) -> None:
        self.waiting.entry_status = QueueEntryStatus.IN_PROGRESS
        self.waiting.save(update_fields=["entry_status", "updated_at"])
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_authorization_invalid_status",
        )

    def test_authorize_requires_appointment_time(self) -> None:
        self.waiting.appointment_time = None
        self.waiting.save(update_fields=["appointment_time", "updated_at"])
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_requires_appointment_time",
        )

    def test_authorize_too_early(self) -> None:
        self.waiting.appointment_time = timezone.now() - timedelta(hours=1)
        self.waiting.save(update_fields=["appointment_time", "updated_at"])
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_authorization_too_early",
        )

    def test_authorize_rejects_when_document_exists(self) -> None:
        session = PatientFormSession.objects.create(
            queue_entry=self.waiting,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.rec,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=self.waiting,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )
        MedicalDocument.objects.create(
            queue_entry=self.waiting,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.medical_document_already_exists_for_queue_entry",
        )

    def test_authorize_rejects_when_submitted_intake_exists(self) -> None:
        session = PatientFormSession.objects.create(
            queue_entry=self.waiting,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.rec,
        )
        PatientIntakeForm.objects.create(
            queue_entry=self.waiting,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_authorization_intake_form_submitted",
        )

    def test_authorize_rejects_duplicate_authorization(self) -> None:
        PaperIntakeAuthorization.objects.create(
            queue_entry=self.waiting,
            authorized_at=timezone.now(),
            authorized_by=self.admin,
            reason=_REASON,
        )
        with self.assertRaises(DomainError) as ctx:
            authorize_paper_intake(
                queue_entry_id=self.waiting.id,
                authorized_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_authorization_already_exists",
        )


class PaperIntakeCreateWithoutIntakeBranchesTests(TestCase):
    def setUp(self) -> None:
        self.admin = StaffUser.objects.create_user(
            username="pic-admin",
            email="pic.admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.doctor = StaffUser.objects.create_user(
            username="pic-doc",
            email="pic.doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.rec = StaffUser.objects.create_user(
            username="pic-rec",
            email="pic.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.rec, "Reception")
        clinic = ClinicSite.objects.create(
            code="PIC", name="Paper Intake Create Clinic"
        )
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.rec,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="C",
            last_name="Patient",
            date_of_birth=date(1991, 2, 2),
            phone="+48222333444",
            email="pic.patient@example.com",
        )
        self.waiting = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.rec,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=self.waiting,
            authorized_at=timezone.now(),
            authorized_by=self.admin,
            reason=_REASON,
        )

    def test_create_without_intake_unknown_user(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.waiting.id,
                created_by_user_id=uuid.uuid4(),
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.staff_user_not_found"
        )

    def test_create_without_intake_invalid_role(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.waiting.id,
                created_by_user_id=self.rec.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_create_document_invalid_role",
        )

    def test_create_without_intake_unknown_queue_entry(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=uuid.uuid4(),
                created_by_user_id=self.doctor.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.queue_entry_not_found"
        )

    def test_create_without_intake_wrong_status(self) -> None:
        self.waiting.entry_status = QueueEntryStatus.IN_PROGRESS
        self.waiting.save(update_fields=["entry_status", "updated_at"])
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.waiting.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.queue_entry_must_be_waiting_for_paper_intake",
        )

    def test_create_without_intake_missing_appointment(self) -> None:
        self.waiting.appointment_time = None
        self.waiting.save(update_fields=["appointment_time", "updated_at"])
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.waiting.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_requires_appointment_time",
        )

    def test_create_without_intake_too_early(self) -> None:
        self.waiting.appointment_time = timezone.now() - timedelta(hours=1)
        self.waiting.save(update_fields=["appointment_time", "updated_at"])
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.waiting.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_earliest_after_appointment",
        )

    def test_create_without_intake_submitted_intake_appeared(self) -> None:
        session = PatientFormSession.objects.create(
            queue_entry=self.waiting,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.rec,
        )
        PatientIntakeForm.objects.create(
            queue_entry=self.waiting,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.waiting.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_intake_form_appeared_after_authorization",
        )

    def test_create_without_intake_not_authorized(self) -> None:
        PaperIntakeAuthorization.objects.filter(queue_entry=self.waiting).delete()
        with self.assertRaises(DomainError) as ctx:
            create_medical_document_without_intake(
                queue_entry_id=self.waiting.id,
                created_by_user_id=self.doctor.id,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_not_authorized",
        )


class PaperIntakeRevokeBranchesTests(TestCase):
    def setUp(self) -> None:
        self.admin = StaffUser.objects.create_user(
            username="pir-admin",
            email="pir.admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.doctor = StaffUser.objects.create_user(
            username="pir-doc",
            email="pir.doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.rec = StaffUser.objects.create_user(
            username="pir-rec",
            email="pir.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.rec, "Reception")
        clinic = ClinicSite.objects.create(
            code="PIR", name="Paper Intake Revoke Clinic"
        )
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.rec,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="R",
            last_name="Patient",
            date_of_birth=date(1992, 3, 3),
            phone="+48333444555",
            email="pir.patient@example.com",
        )
        self.waiting = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.rec,
        )
        self.auth = PaperIntakeAuthorization.objects.create(
            queue_entry=self.waiting,
            authorized_at=timezone.now(),
            authorized_by=self.admin,
            reason=_REASON,
        )

    def test_revoke_unknown_actor(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            revoke_paper_intake_authorization(
                queue_entry_id=self.waiting.id,
                revoked_by_user_id=uuid.uuid4(),
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.staff_user_not_found"
        )

    def test_revoke_invalid_role(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            revoke_paper_intake_authorization(
                queue_entry_id=self.waiting.id,
                revoked_by_user_id=self.doctor.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_authorization_invalid_role",
        )

    def test_revoke_unknown_queue_entry(self) -> None:
        with self.assertRaises(DomainError) as ctx:
            revoke_paper_intake_authorization(
                queue_entry_id=uuid.uuid4(),
                revoked_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key, "other.api.queue_entry_not_found"
        )

    def test_revoke_when_no_authorization(self) -> None:
        self.auth.delete()
        with self.assertRaises(DomainError) as ctx:
            revoke_paper_intake_authorization(
                queue_entry_id=self.waiting.id,
                revoked_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_authorization_not_found",
        )

    def test_revoke_after_document_created(self) -> None:
        self.auth.delete()
        doc = MedicalDocument.objects.create(
            queue_entry=self.waiting,
            intake_form=None,
            source_type=MedicalDocumentSourceType.PAPER_INTAKE,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        PaperIntakeAuthorization.objects.create(
            queue_entry=self.waiting,
            authorized_at=timezone.now(),
            authorized_by=self.admin,
            reason=_REASON,
        )
        with self.assertRaises(DomainError) as ctx:
            revoke_paper_intake_authorization(
                queue_entry_id=self.waiting.id,
                revoked_by_user_id=self.admin.id,
                reason=_REASON,
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.paper_intake_revoke_after_document_created",
        )
        self.assertTrue(MedicalDocument.objects.filter(id=doc.id).exists())
