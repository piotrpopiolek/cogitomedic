"""Tests for apps/intake/retention_services.py."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.intake.models import (
    IntakeDocumentVersion,
    IntakePdfStatus,
    PatientIntakeForm,
)
from apps.intake.retention_services import run_intake_retention_cleanup
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


def _make_intake_version(
    *,
    reception_user: StaffUser,
    hidrive_sent: bool = True,
    pdf_local_path: str | None = None,
    days_old: int = 35,
) -> IntakeDocumentVersion:
    """Create a minimal IntakeDocumentVersion with created_at backdated by days_old."""
    clinic = ClinicSite.objects.create(
        code=f"RET{days_old}{hidrive_sent}",
        name="Retention Clinic",
    )
    room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
    queue = DailyQueue.objects.create(
        queue_date=timezone.now().date(),
        clinic_site=clinic,
        consulting_room=room,
        status=QueueStatus.OPEN,
        created_by_user=reception_user,
    )
    patient = Patient.objects.create(
        first_name="Ret",
        last_name="Patient",
        date_of_birth=date(1985, 6, 15),
        phone=f"004912345{timezone.now().microsecond:06d}"[:15],
        email=f"ret{timezone.now().microsecond}@example.com",
        doctolib_patient_id=f"RET-{timezone.now().microsecond}",
    )
    entry = QueueEntry.objects.create(
        daily_queue=queue,
        patient=patient,
        position_no=1,
        entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        created_by_user=reception_user,
    )
    session = PatientFormSession.objects.create(
        queue_entry=entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(minutes=60),
        created_by_user_id=reception_user.id,
    )
    intake_form = PatientIntakeForm.objects.create(
        queue_entry=entry,
        session=session,
        form_status="SUBMITTED",
        submitted_at=timezone.now(),
        signature_file_path="signatures/test/dummy.png",
        anamnesis_payload={"answers": [{"key": "age", "value": "40"}]},
        body_map_data=[{"lesion_no": 1}],
    )
    version = IntakeDocumentVersion.objects.create(
        intake_form=intake_form,
        version_no=1,
        form_locale="de-DE",
        pdf_generation_status=IntakePdfStatus.COMPLETED,
        # COMPLETED requires a non-null path (DB constraint)
        pdf_local_path=pdf_local_path or "pdfs/intake/placeholder.pdf",
        hidrive_sent=hidrive_sent,
        # hidrive_sent=True requires hidrive_sent_at (DB constraint)
        hidrive_sent_at=timezone.now() if hidrive_sent else None,
        snapshot_payload={"patient": {"first_name": "Ret"}},
    )
    # Backdate created_at past the threshold so it qualifies as a retention candidate
    past = timezone.now() - timedelta(days=days_old)
    IntakeDocumentVersion.objects.filter(id=version.id).update(created_at=past)
    version.refresh_from_db()
    return version


class IntakeRetentionServicesTests(TestCase):
    def setUp(self) -> None:
        self.reception_user = StaffUser.objects.create_user(
            username="retention-reception",
            email="retention@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def test_raises_domain_error_on_zero_days(self) -> None:
        with self.assertRaises(DomainError):
            run_intake_retention_cleanup(older_than_days=0, dry_run=True)

    def test_raises_domain_error_on_negative_days(self) -> None:
        with self.assertRaises(DomainError):
            run_intake_retention_cleanup(older_than_days=-5, dry_run=True)

    # ------------------------------------------------------------------
    # No candidates
    # ------------------------------------------------------------------

    def test_empty_database_returns_zero_candidates(self) -> None:
        result = run_intake_retention_cleanup(older_than_days=30, dry_run=True)
        self.assertEqual(result.candidates, 0)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(result.skipped_not_safe, 0)

    def test_recent_version_not_a_candidate(self) -> None:
        """A version created today is newer than the threshold and is not a candidate."""
        clinic = ClinicSite.objects.create(code="NEW1", name="New Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="N1", name="N1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )
        patient = Patient.objects.create(
            first_name="New",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="49111111111",
            email="newpatient@example.com",
            doctolib_patient_id="NEW-PAT-1",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            position_no=1,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            created_by_user=self.reception_user,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(minutes=60),
            created_by_user_id=self.reception_user.id,
        )
        intake_form = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status="SUBMITTED",
            submitted_at=timezone.now(),
            signature_file_path="signatures/test/new.png",
        )
        IntakeDocumentVersion.objects.create(
            intake_form=intake_form,
            version_no=1,
            form_locale="de-DE",
            pdf_generation_status=IntakePdfStatus.COMPLETED,
            pdf_local_path="pdfs/intake/placeholder_new.pdf",
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            snapshot_payload={},
        )
        result = run_intake_retention_cleanup(older_than_days=30, dry_run=True)
        self.assertEqual(result.candidates, 0)

    # ------------------------------------------------------------------
    # dry_run=True — nie usuwa
    # ------------------------------------------------------------------

    def test_dry_run_does_not_delete_eligible_version(self) -> None:
        version = _make_intake_version(
            reception_user=self.reception_user,
            hidrive_sent=True,
            days_old=35,
        )
        result = run_intake_retention_cleanup(older_than_days=30, dry_run=True)
        self.assertEqual(result.candidates, 1)
        self.assertEqual(result.deleted, 0)
        version.refresh_from_db()
        self.assertIsNone(version.local_pdf_deleted_at)

    # ------------------------------------------------------------------
    # Skipped — not on HiDrive
    # ------------------------------------------------------------------

    def test_version_not_on_hidrive_is_skipped(self) -> None:
        _make_intake_version(
            reception_user=self.reception_user,
            hidrive_sent=False,
            days_old=40,
        )
        result = run_intake_retention_cleanup(older_than_days=30, dry_run=False)
        self.assertEqual(result.candidates, 1)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(result.skipped_not_safe, 1)

    # ------------------------------------------------------------------
    # Real deletion — plik na dysku zostaje usunięty
    # ------------------------------------------------------------------

    def test_eligible_version_is_deleted_and_payloads_cleared(self) -> None:
        pdf_dir = Path(settings.MEDIA_ROOT) / "pdfs" / "intake" / "test_retention"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_file = pdf_dir / "dummy_retention.pdf"
        pdf_file.write_bytes(b"%PDF-1.0 minimal test\n")
        rel_path = str(pdf_file.relative_to(Path(settings.MEDIA_ROOT)))

        version = _make_intake_version(
            reception_user=self.reception_user,
            hidrive_sent=True,
            pdf_local_path=rel_path,
            days_old=35,
        )
        intake_form_id = version.intake_form_id

        result = run_intake_retention_cleanup(older_than_days=30, dry_run=False)

        self.assertEqual(result.deleted, 1)
        self.assertEqual(result.skipped_not_safe, 0)

        version.refresh_from_db()
        self.assertIsNotNone(version.local_pdf_deleted_at)
        self.assertIsNone(version.pdf_local_path)
        self.assertTrue(version.snapshot_payload.get("cleared_at_retention"))

        # Anamnesis payload cleared
        intake_form = PatientIntakeForm.objects.get(id=intake_form_id)
        self.assertEqual(intake_form.anamnesis_payload, {})
        self.assertEqual(intake_form.body_map_data, [])

        # Physical file removed
        self.assertFalse(pdf_file.exists())
