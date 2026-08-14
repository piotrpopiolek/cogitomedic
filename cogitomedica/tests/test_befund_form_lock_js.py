"""Static contract: doctor befund-form.js edit-lock release policy (P0 + review fixes)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
)
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

    def test_no_two_second_flag_clear_timer(self) -> None:
        src = self._js_source()
        self.assertNotIn("releaseLockOnNextPageHide", src)
        self.assertNotIn("markIntentionalLeaveForLockRelease", src)
        self.assertNotRegex(
            src, r"setTimeout\(\s*function\s*\(\)\s*\{[^}]{0,80}releaseLock"
        )

    def test_pagehide_skips_bfcache_but_unlocks_real_unload(self) -> None:
        src = self._js_source()
        self.assertIn('window.addEventListener("pagehide"', src)
        self.assertIn("e.persisted", src)
        self.assertIn("if (e && e.persisted) return;", src)
        # Must still call unlock on non-persisted pagehide (Back / close / navigate).
        pagehide_idx = src.index('window.addEventListener("pagehide"')
        chunk = src[pagehide_idx : pagehide_idx + 280]
        self.assertIn("releaseEditLockBestEffort", chunk)

    def test_no_visibilitychange_unlock(self) -> None:
        src = self._js_source()
        self.assertNotIn("visibilitychange", src)

    def test_conscious_exit_unlocks_immediately(self) -> None:
        src = self._js_source()
        self.assertIn("js-release-document-lock", src)
        self.assertIn("releaseEditLockOnIntentionalLeave", src)
        self.assertIn("releaseEditLockBestEffort", src)
        # Logout path must unlock immediately (slow POST must not wait on pagehide).
        self.assertIn("Logout POST can be slow", src)
        self.assertIn('addEventListener("beforeunload"', src)
        beforeunload_idx = src.index('addEventListener("beforeunload"')
        chunk = src[beforeunload_idx : beforeunload_idx + 350]
        self.assertNotIn("releaseEditLock", chunk)
        self.assertNotIn("/unlock", chunk)

    def test_draft_save_clears_dirty_flag(self) -> None:
        src = self._js_source()
        # Successful save-draft path must clear dirty so beforeunload is not shown.
        marker = (
            "previewSeenSinceLastSave = false;\n"
            "            befundFormDirty = false;\n"
            "            applyRevisionStateFromResponse"
        )
        self.assertIn(marker, src)

    def test_intake_summary_renders_reception_note_after_anamnesis(self) -> None:
        src = self._js_source()
        self.assertIn('el("intake-reception-note")', src)
        self.assertIn("summaryEl.appendChild(noteSlot)", src)
        anamnesis_idx = src.index("intakeAnamnesisHeading")
        note_idx = src.index("intake-reception-note")
        body_map_idx = src.index("renderReadonlyBodyMapHtml(bodyMapPts")
        self.assertLess(anamnesis_idx, note_idx)
        self.assertLess(note_idx, body_map_idx)
        self.assertIn("whitespace-pre-wrap", src)
        self.assertIn("CTX.intake_summary && CTX.intake_summary.reception_note", src)

    def test_intake_summary_reception_note_not_gated_on_revision_or_draft(self) -> None:
        """Empfangsnotiz is painted from CTX on load, including pending revision."""
        src = self._js_source()
        summary_idx = src.index("if (CTX && CTX.intake_summary)")
        note_idx = src.index('el("intake-reception-note")')
        skip_form_idx = src.index("var skipBefundFormUi")
        self.assertLess(summary_idx, note_idx)
        self.assertLess(note_idx, skip_form_idx)
        block = src[summary_idx:skip_form_idx]
        self.assertNotIn("hasPendingRevision", block)
        self.assertNotIn("isDraftAuthoring", block)
        self.assertNotIn("docStatus", block)


class DocumentLockWithoutPagehideReleaseTests(TestCase):
    """A keeps the lock without client unlock (tab in background / bfcache); B cannot acquire."""

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

        granted_b, holder = acquire_document_lock(
            medical_document_id=self.doc.id, user=self.doctor_b
        )
        self.assertFalse(granted_b)
        self.assertTrue(bool(holder))

    def test_explicit_unlock_allows_second_doctor_acquire(self) -> None:
        acquire_document_lock(medical_document_id=self.doc.id, user=self.doctor_a)
        self.assertTrue(
            release_document_lock(medical_document_id=self.doc.id, user=self.doctor_a)
        )
        granted_b, _ = acquire_document_lock(
            medical_document_id=self.doc.id, user=self.doctor_b
        )
        self.assertTrue(granted_b)
