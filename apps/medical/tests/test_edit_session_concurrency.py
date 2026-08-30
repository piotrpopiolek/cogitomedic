"""Concurrent edit-session / write-gate behaviour (PostgreSQL + threading)."""

from __future__ import annotations

import threading
import uuid
from datetime import date, timedelta

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.constants import (
    DOCUMENT_LOCK_TIMEOUT_HOURS,
    DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
)
from apps.medical.edit_session import (
    EditSessionResponseError,
    count_doctor_active_document_locks,
    start_doctor_edit_session,
)
from apps.medical.models import MedicalDocStatus, MedicalDocument
from apps.medical.write_gate import mutate_doctor_save_draft
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


class EditSessionConcurrencyTests(TransactionTestCase):
    def setUp(self) -> None:
        self.doctor_a = StaffUser.objects.create_user(
            username="conc-doc-a",
            email="conc-a@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_a, "Doctor")
        self.doctor_b = StaffUser.objects.create_user(
            username="conc-doc-b",
            email="conc-b@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_b, "Doctor")
        self.clinic = ClinicSite.objects.create(code="CNC", name="Concurrent Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="R1", name="R1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=date.today(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor_a,
            created_by_user=self.doctor_a,
        )
        self._pos = 0

    def _make_draft(self) -> MedicalDocument:
        self._pos += 1
        suffix = uuid.uuid4().hex[:8]
        patient = Patient.objects.create(
            first_name="Conc",
            last_name=f"P{suffix}",
            date_of_birth=date(1988, 3, 3),
            phone=f"49171{suffix[:8]}",
            email=f"conc.{suffix}@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=self._pos,
            created_by_user=self.doctor_a,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor_a,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="c" * 64,
        )
        return MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor_a,
        )

    @staticmethod
    def _payload(**extra) -> dict:
        body = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        body.update(extra)
        return body

    def test_two_doctors_acquire_same_doc_one_holder(self) -> None:
        doc = self._make_draft()
        results: list[object] = []
        errors: list[str] = []
        barrier = threading.Barrier(2)

        def acquire(user: StaffUser) -> None:
            try:
                barrier.wait(timeout=10)
                result = start_doctor_edit_session(
                    medical_document_id=doc.id, user=user, purpose="edit"
                )
                results.append(result)
            except EditSessionResponseError as exc:
                errors.append(exc.error_key)
            finally:
                connection.close()

        t1 = threading.Thread(target=acquire, args=(self.doctor_a,))
        t2 = threading.Thread(target=acquire, args=(self.doctor_b,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, ["document_locked_by_other"])
        doc.refresh_from_db()
        self.assertIsNotNone(doc.locked_by_user_id)
        self.assertEqual(
            count_doctor_active_document_locks(user_id=doc.locked_by_user_id), 1
        )

    def test_parallel_reclaim_one_token_and_stale_revision_superseded(self) -> None:
        doc = self._make_draft()
        first = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor_a, purpose="edit"
        )
        base_rev = first.edit_session_revision
        results: list[object] = []
        errors: list[str] = []
        barrier = threading.Barrier(2)

        def reclaim() -> None:
            try:
                barrier.wait(timeout=10)
                result = start_doctor_edit_session(
                    medical_document_id=doc.id,
                    user=self.doctor_a,
                    purpose="edit",
                    reclaim_confirmed=True,
                    expected_edit_session_revision=base_rev,
                    edit_session_request_id=uuid.uuid4(),
                )
                results.append(result.edit_session_token)
            except EditSessionResponseError as exc:
                errors.append(exc.error_key)
            finally:
                connection.close()

        t1 = threading.Thread(target=reclaim)
        t2 = threading.Thread(target=reclaim)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 1)
        self.assertEqual(errors, ["reclaim_superseded"])
        doc.refresh_from_db()
        self.assertEqual(doc.edit_session_token, results[0])

        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id,
                user=self.doctor_a,
                purpose="edit",
                reclaim_confirmed=True,
                expected_edit_session_revision=base_rev,
                edit_session_request_id=uuid.uuid4(),
            )
        self.assertEqual(ctx.exception.error_key, "reclaim_superseded")

    def test_four_parallel_acquires_at_most_three_locks(self) -> None:
        docs = [self._make_draft() for _ in range(4)]
        ok: list[uuid.UUID] = []
        errors: list[str] = []
        barrier = threading.Barrier(4)
        lock = threading.Lock()

        def acquire(document: MedicalDocument) -> None:
            try:
                barrier.wait(timeout=15)
                start_doctor_edit_session(
                    medical_document_id=document.id,
                    user=self.doctor_a,
                    purpose="edit",
                )
                with lock:
                    ok.append(document.id)
            except EditSessionResponseError as exc:
                with lock:
                    errors.append(exc.error_key)
            finally:
                connection.close()

        threads = [
            threading.Thread(target=acquire, args=(document,)) for document in docs
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(ok), DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS)
        self.assertEqual(errors, ["doctor_lock_limit_reached"])
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor_a.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )

    def test_parallel_identical_draft_save_request_id_replays_once(self) -> None:
        doc = self._make_draft()
        sess = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor_a, purpose="edit"
        )
        request_id = uuid.uuid4()
        base_rev = sess.draft_revision
        results: list[tuple[int, bool]] = []
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        def save() -> None:
            try:
                barrier.wait(timeout=10)
                result = mutate_doctor_save_draft(
                    medical_document_id=doc.id,
                    user=self.doctor_a,
                    edit_session_token=sess.edit_session_token,
                    expected_draft_revision=base_rev,
                    draft_save_request_id=request_id,
                    medical_payload_schema_version=1,
                    medical_payload=self._payload(summary_text="parallel"),
                    diagnosis_code=None,
                    procedure_code=None,
                    intent="edit",
                )
                with lock:
                    results.append((result.draft_revision, result.replayed))
            finally:
                connection.close()

        t1 = threading.Thread(target=save)
        t2 = threading.Thread(target=save)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 2)
        revisions = {item[0] for item in results}
        self.assertEqual(len(revisions), 1)
        self.assertEqual(sum(1 for _, replayed in results if not replayed), 1)
        self.assertEqual(sum(1 for _, replayed in results if replayed), 1)
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, results[0][0])
        self.assertEqual(doc.last_draft_request_id, request_id)
        draft_audits = AuditEvent.objects.filter(
            medical_document_id=doc.id, event_type="DOCUMENT_DRAFT_SAVED"
        ).count()
        self.assertEqual(draft_audits, 1)

    def test_parallel_save_same_revision_one_success_one_conflict(self) -> None:
        doc = self._make_draft()
        sess = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor_a, purpose="edit"
        )
        base_rev = sess.draft_revision
        successes: list[int] = []
        errors: list[str] = []
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        def save(note: str) -> None:
            try:
                barrier.wait(timeout=10)
                result = mutate_doctor_save_draft(
                    medical_document_id=doc.id,
                    user=self.doctor_a,
                    edit_session_token=sess.edit_session_token,
                    expected_draft_revision=base_rev,
                    draft_save_request_id=uuid.uuid4(),
                    medical_payload_schema_version=1,
                    medical_payload=self._payload(summary_text=note),
                    intent="edit",
                )
                with lock:
                    successes.append(result.draft_revision)
            except EditSessionResponseError as exc:
                with lock:
                    errors.append(exc.error_key)
            finally:
                connection.close()

        t1 = threading.Thread(target=save, args=("race-a",))
        t2 = threading.Thread(target=save, args=("race-b",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(successes), 1)
        self.assertEqual(errors, ["draft_revision_conflict"])
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, successes[0])

    def test_expired_lock_replaced_emits_single_audit_event(self) -> None:
        doc = self._make_draft()
        start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor_a, purpose="edit"
        )
        MedicalDocument.objects.filter(id=doc.id).update(
            locked_at=timezone.now() - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS + 1)
        )
        AuditEvent.objects.filter(
            medical_document_id=doc.id,
            event_type="DOCUMENT_LOCK_EXPIRED_REPLACED",
        ).delete()

        start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor_b, purpose="edit"
        )
        events = list(
            AuditEvent.objects.filter(
                medical_document_id=doc.id,
                event_type="DOCUMENT_LOCK_EXPIRED_REPLACED",
            )
        )
        self.assertEqual(len(events), 1)
        doc.refresh_from_db()
        self.assertEqual(doc.locked_by_user_id, self.doctor_b.id)

    def test_parallel_amend_creates_one_pending_and_one_holder(self) -> None:
        doc = self._make_draft()
        now = timezone.now()
        from apps.medical.models import (
            DocVersionStatus,
            MedicalDocStatus,
            MedicalDocumentVersion,
            PdfStatus,
        )

        MedicalDocumentVersion.objects.create(
            medical_document=doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload=self._payload(),
            published_at=now,
            publish_locale="de-DE",
            published_by_user=self.doctor_a,
            publish_request_id=uuid.uuid4(),
            pdf_local_path="/media/befund/parallel-amend.pdf",
            hidrive_sent=True,
            hidrive_sent_at=now,
            sms_sent=True,
            sms_sent_at=now,
        )
        MedicalDocument.objects.filter(id=doc.id).update(
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            published_version_no=1,
            has_pending_revision=False,
            created_by_user=self.doctor_a,
        )
        # Publisher-only amend: doctor_a is publisher.
        MedicalDocumentVersion.objects.filter(
            medical_document_id=doc.id, version_no=1
        ).update(published_by_user=self.doctor_a)

        ok: list[str] = []
        errors: list[str] = []
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        def amend(user: StaffUser) -> None:
            try:
                barrier.wait(timeout=15)
                start_doctor_edit_session(
                    medical_document_id=doc.id, user=user, purpose="amend"
                )
                with lock:
                    ok.append(str(user.id))
            except Exception as exc:
                with lock:
                    errors.append(
                        type(exc).__name__
                        + ":"
                        + str(
                            getattr(
                                exc, "error_key", getattr(exc, "api_message_key", exc)
                            )
                        )
                    )
            finally:
                connection.close()

        # Same publisher racing itself (two tabs).
        t1 = threading.Thread(target=amend, args=(self.doctor_a,))
        t2 = threading.Thread(target=amend, args=(self.doctor_a,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(ok), 1, msg=f"ok={ok} errors={errors}")
        self.assertEqual(len(errors), 1, msg=f"ok={ok} errors={errors}")
        doc.refresh_from_db()
        self.assertTrue(doc.has_pending_revision)
        self.assertEqual(doc.locked_by_user_id, self.doctor_a.id)
        pending = MedicalDocumentVersion.objects.filter(
            medical_document_id=doc.id,
            version_status=DocVersionStatus.DRAFT,
        ).count()
        self.assertEqual(pending, 1)
