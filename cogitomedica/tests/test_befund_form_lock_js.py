"""Static contract: doctor befund-form.js must not unlock on bare pagehide (P0)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.medical.models import MedicalDocStatus, MedicalDocument, MedicalDocumentSourceType
from apps.medical.services import acquire_document_lock, release_document_lock
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueueStatus,
)
from apps.users.models import StaffUser


class BefundFormLockJsContractTests(SimpleTestCase):
    def _js_source(self) -> str:
        path = Path(settings.BASE_DIR) / "static" / "doctor" / "js" / "befund-form.js"
        return path.read_text(encoding="utf-8")

    def test_pagehide_does_not_unconditionally_unlock(self) -> None:
        src = self._js_source()
        self.assertIn("releaseLockOnNextPageHide", src)
        self.assertIn('window.addEventListener("pagehide"', src)
        # Guard: unlock on pagehide only when intentional-leave flag is set.
        self.assertIn("if (!releaseLockOnNextPageHide) return;", src)
        self.assertNotRegex(
            src,
            r'addEventListener\(\s*"pagehide"\s*,\s*releaseEditLock',
        )

    def test_no_visibilitychange_unlock(self) -> None:
        src = self._js_source()
        self.assertNotIn("visibilitychange", src)

    def test_conscious_exit_hooks_present(self) -> None:
        src = self._js_source()
        self.assertIn("js-release-document-lock", src)
        self.assertIn("markIntentionalLeaveForLockRelease", src)
        self.assertIn("releaseEditLockBestEffort", src)
        self.assertIn('addEventListener("beforeunload"', src)
        beforeunload_idx = src.index('addEventListener("beforeunload"')
        chunk = src[beforeunload_idx : beforeunload_idx + 350]
        self.assertNotIn("releaseEditLock", chunk)
        self.assertNotIn("/unlock", chunk)


class DocumentLockWithoutPagehideReleaseTests(TestCase):
    """A keeps the lock without client unlock (tab in background); B cannot acquire."""

    def setUp(self) -> None:
        self.doctor_a = StaffUser.objects.create_user(
            username="lock-doc-a",
            email="lock.a@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_a, "Doctor")
        self.doctor_b = StaffUser.objects.create_user(
            username="lock-doc-b",
            email="lock.b@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_b, "Doctor")
        clinic = ClinicSite.objects.create(code="LCK", name="Lock Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="L1", name="L1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.doctor_a,
        )
        patient = Patient.objects.create(
            first_name="Lock",
            last_name="Patient",
            date_of_birth=date(1980, 1, 1),
            phone="+49111111111",
            email="lock.patient@example.com",
            doctolib_patient_id="DOC-LOCK-1",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.doctor_a,
        )
        self.doc = MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=None,
            source_type=MedicalDocumentSourceType.PAPER_INTAKE,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor_a,
            updated_by_user=self.doctor_a,
        )

    def test_b_cannot_acquire_while_a_holds_lock_without_release(self) -> None:
        granted_a, _ = acquire_document_lock(
            medical_document_id=self.doc.id, user=self.doctor_a
        )
        self.assertTrue(granted_a)

        # No release — models "tab still open in background" (P0: no pagehide unlock).
        granted_b, holder = acquire_document_lock(
            medical_document_id=self.doc.id, user=self.doctor_b
        )
        self.assertFalse(granted_b)
        self.assertTrue(bool(holder))

    def test_explicit_unlock_allows_second_doctor_acquire(self) -> None:
        acquire_document_lock(medical_document_id=self.doc.id, user=self.doctor_a)
        self.assertTrue(
            release_document_lock(
                medical_document_id=self.doc.id, user=self.doctor_a
            )
        )
        granted_b, _ = acquire_document_lock(
            medical_document_id=self.doc.id, user=self.doctor_b
        )
        self.assertTrue(granted_b)
