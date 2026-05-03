from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    MedicalDocument,
    MedicalDocumentSourceType,
    PaperIntakeAuthorization,
)
from apps.medical.constants import PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT
from apps.medical.paper_intake_policy import paper_intake_authorize_eligibility
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

_AUTH_REASON = (
    "Paper intake policy test authorization reason long enough for validation."
)


class PaperIntakeAuthorizeEligibilityTests(TestCase):
    def setUp(self) -> None:
        self.staff = StaffUser.objects.create_user(
            username="pol-staff",
            email="pol.staff@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.staff, "Reception")
        self.doctor = StaffUser.objects.create_user(
            username="pol-doc",
            email="pol.doc@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        clinic = ClinicSite.objects.create(code="POL", name="Policy Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.staff,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="Pol",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="+48111222333",
            email="pol.patient@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now()
            - timedelta(hours=PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT + 1),
            created_by_user=self.staff,
        )

    def test_can_authorize_when_waiting_and_past_delay(self) -> None:
        e = paper_intake_authorize_eligibility(entry=self.entry)
        self.assertFalse(e.has_document)
        self.assertIsNone(e.active_authorization)
        self.assertTrue(e.can_authorize)
        self.assertFalse(e.can_revoke)
        self.assertEqual(e.blocking_blocks, ())
        self.assertIsNotNone(e.earliest_authorize_at)

    def test_blocks_when_not_waiting(self) -> None:
        self.entry.entry_status = QueueEntryStatus.IN_PROGRESS
        self.entry.save(update_fields=["entry_status", "updated_at"])
        e = paper_intake_authorize_eligibility(entry=self.entry)
        self.assertFalse(e.can_authorize)
        self.assertEqual(
            e.blocking_blocks[0].message_key,
            "other.domain.paper_intake_authorization_invalid_status",
        )

    def test_blocks_when_no_appointment_time(self) -> None:
        self.entry.appointment_time = None
        self.entry.save(update_fields=["appointment_time", "updated_at"])
        e = paper_intake_authorize_eligibility(entry=self.entry)
        self.assertFalse(e.can_authorize)
        keys = {b.message_key for b in e.blocking_blocks}
        self.assertIn("other.domain.paper_intake_requires_appointment_time", keys)

    def test_blocks_when_before_earliest_authorize_moment(self) -> None:
        self.entry.appointment_time = timezone.now() + timedelta(hours=1)
        self.entry.save(update_fields=["appointment_time", "updated_at"])
        e = paper_intake_authorize_eligibility(entry=self.entry)
        self.assertFalse(e.can_authorize)
        too_early = e.blocking_blocks[-1]
        self.assertEqual(
            too_early.message_key,
            "other.domain.paper_intake_authorization_too_early",
        )
        self.assertEqual(
            too_early.format_params.get("hours"),
            PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT,
        )
        self.assertIsNotNone(e.earliest_authorize_at)

    def test_blocks_when_intake_submitted(self) -> None:
        session = PatientFormSession.objects.create(
            queue_entry=self.entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=30),
            consumed_at=timezone.now(),
            created_by_user=self.staff,
        )
        PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/sig.png",
            signature_sha256="b" * 64,
            submitted_at=timezone.now(),
            anamnesis_payload={"schema_version": 1, "answers": []},
        )
        e = paper_intake_authorize_eligibility(entry=self.entry)
        self.assertFalse(e.can_authorize)
        self.assertEqual(
            e.blocking_blocks[-1].message_key,
            "other.domain.paper_intake_authorization_intake_form_submitted",
        )

    def test_has_document_branch(self) -> None:
        MedicalDocument.objects.create(
            queue_entry=self.entry,
            intake_form=None,
            source_type=MedicalDocumentSourceType.PAPER_INTAKE,
            created_by_user=self.staff,
        )
        e = paper_intake_authorize_eligibility(entry=self.entry)
        self.assertTrue(e.has_document)
        self.assertFalse(e.can_authorize)
        self.assertFalse(e.can_revoke)
        self.assertEqual(
            e.blocking_blocks[0].message_key,
            "administration.paper_intake_admin_has_document",
        )

    def test_active_authorization_revoke_branch(self) -> None:
        admin = StaffUser.objects.create_user(
            username="pol-adm",
            email="pol.adm@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(admin, "Admin")
        PaperIntakeAuthorization.objects.create(
            queue_entry=self.entry,
            authorized_at=timezone.now(),
            authorized_by=admin,
            reason=_AUTH_REASON,
        )
        e = paper_intake_authorize_eligibility(entry=self.entry)
        self.assertFalse(e.has_document)
        self.assertIsNotNone(e.active_authorization)
        self.assertFalse(e.can_authorize)
        self.assertTrue(e.can_revoke)
        self.assertEqual(e.blocking_blocks, ())
