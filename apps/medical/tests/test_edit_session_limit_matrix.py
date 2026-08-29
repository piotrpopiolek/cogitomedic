"""Full doctor lock-limit matrix (ENTWURF + pending revisions)."""

from __future__ import annotations

import uuid
from datetime import timedelta

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
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.medical.tests.test_services_coverage import ServicesCoverageBase
from apps.medical.write_gate import (
    mark_doctor_draft_previewed,
    mutate_doctor_discard_revision,
    mutate_doctor_publish,
    mutate_doctor_save_draft,
)
from apps.reception.models import PatientFormSession, QueueEntryStatus
from apps.users.models import StaffUser


class DoctorLockLimitMatrixTests(ServicesCoverageBase):
    def _payload(self, **extra) -> dict:
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

    def _make_draft(self) -> MedicalDocument:
        qe = self._make_queue_entry(
            position_no=self._next_queue_position_no(),
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        )
        session = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="l" * 64,
        )
        return MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )

    def _make_published(self, *, doctor: StaffUser | None = None) -> MedicalDocument:
        actor = doctor or self.doctor
        doc = self._make_draft()
        if actor.id != self.doctor.id:
            MedicalDocument.objects.filter(id=doc.id).update(created_by_user=actor)
            doc.refresh_from_db()
        now = timezone.now()
        MedicalDocumentVersion.objects.create(
            medical_document=doc,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload=self._payload(),
            published_at=now,
            publish_locale="de-DE",
            published_by_user=actor,
            publish_request_id=uuid.uuid4(),
            pdf_local_path="/media/befund/limit-matrix.pdf",
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
        )
        doc.refresh_from_db()
        return doc

    def _other_doctor(self, suffix: str) -> StaffUser:
        user = StaffUser.objects.create_user(
            username=f"lim-{suffix}",
            email=f"lim-{suffix}@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(user, "Doctor")
        return user

    def test_slots_zero_through_three_then_block(self) -> None:
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id), 0
        )
        held = []
        for i in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS):
            doc = self._make_draft()
            start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
            held.append(doc)
            self.assertEqual(
                count_doctor_active_document_locks(user_id=self.doctor.id), i + 1
            )
        fourth = self._make_draft()
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=fourth.id, user=self.doctor, purpose="edit"
            )
        self.assertEqual(ctx.exception.error_key, "doctor_lock_limit_reached")
        fourth.refresh_from_db()
        self.assertIsNone(fourth.locked_by_user_id)
        for doc in held:
            doc.refresh_from_db()
            self.assertEqual(doc.locked_by_user_id, self.doctor.id)

    def test_mixed_draft_and_open_revision_consume_same_limit(self) -> None:
        draft_a = self._make_draft()
        draft_b = self._make_draft()
        published = self._make_published()
        start_doctor_edit_session(
            medical_document_id=draft_a.id, user=self.doctor, purpose="edit"
        )
        start_doctor_edit_session(
            medical_document_id=draft_b.id, user=self.doctor, purpose="edit"
        )
        start_doctor_edit_session(
            medical_document_id=published.id, user=self.doctor, purpose="amend"
        )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )
        extra = self._make_draft()
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=extra.id, user=self.doctor, purpose="edit"
            )
        self.assertEqual(ctx.exception.error_key, "doctor_lock_limit_reached")
        locked = ctx.exception.payload.get("locked_documents") or []
        self.assertEqual(len(locked), DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS)
        statuses = {item["status"] for item in locked}
        self.assertIn(MedicalDocStatus.DRAFT, statuses)
        self.assertIn(MedicalDocStatus.PUBLISHED, statuses)

    def test_three_locks_plus_expired_frees_a_slot(self) -> None:
        docs = [self._make_draft() for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS)]
        for doc in docs:
            start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
        MedicalDocument.objects.filter(id=docs[0].id).update(
            locked_at=timezone.now()
            - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS + 1)
        )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS - 1,
        )
        replacement = self._make_draft()
        start_doctor_edit_session(
            medical_document_id=replacement.id, user=self.doctor, purpose="edit"
        )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )

    def test_resume_and_reclaim_do_not_consume_extra_slot(self) -> None:
        docs = [self._make_draft() for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS)]
        tokens = []
        for doc in docs:
            result = start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
            tokens.append(result)
        resumed = start_doctor_edit_session(
            medical_document_id=docs[0].id,
            user=self.doctor,
            purpose="edit",
            edit_session_token=tokens[0].edit_session_token,
        )
        self.assertEqual(resumed.mode, "resumed")
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )
        reclaimed = start_doctor_edit_session(
            medical_document_id=docs[1].id,
            user=self.doctor,
            purpose="edit",
            reclaim_confirmed=True,
            expected_edit_session_revision=tokens[1].edit_session_revision,
            edit_session_request_id=uuid.uuid4(),
        )
        self.assertEqual(reclaimed.mode, "reclaimed")
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )

    def test_publish_and_discard_free_a_slot(self) -> None:
        drafts = [self._make_draft() for _ in range(2)]
        for doc in drafts:
            start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
        pub = self._make_published()
        sess = start_doctor_edit_session(
            medical_document_id=pub.id, user=self.doctor, purpose="amend"
        )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id), 3
        )
        mutate_doctor_discard_revision(
            medical_document_id=pub.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=sess.draft_revision,
        )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id), 2
        )

        target = drafts[0]
        target.refresh_from_db()
        token = target.edit_session_token
        assert token is not None
        saved = mutate_doctor_save_draft(
            medical_document_id=target.id,
            user=self.doctor,
            edit_session_token=token,
            expected_draft_revision=target.draft_revision,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="pub-slot"),
        )
        mark_doctor_draft_previewed(
            medical_document_id=target.id,
            user=self.doctor,
            edit_session_token=token,
            expected_draft_revision=saved.draft_revision,
        )
        mutate_doctor_publish(
            medical_document_id=target.id,
            user=self.doctor,
            edit_session_token=token,
            expected_draft_revision=saved.draft_revision,
            publish_request_id=uuid.uuid4(),
            publish_locale="de-DE",
        )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id), 1
        )
        freed = self._make_draft()
        start_doctor_edit_session(
            medical_document_id=freed.id, user=self.doctor, purpose="edit"
        )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id), 2
        )

    def test_two_doctors_have_independent_limits(self) -> None:
        other = self._other_doctor("indep")
        for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS):
            doc = self._make_draft()
            start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
        for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS):
            doc = self._make_draft()
            start_doctor_edit_session(
                medical_document_id=doc.id, user=other, purpose="edit"
            )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=other.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )

    def test_limit_does_not_auto_release_oldest_document(self) -> None:
        docs = [self._make_draft() for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS)]
        for doc in docs:
            start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
        oldest_id = docs[0].id
        MedicalDocument.objects.filter(id=oldest_id).update(
            locked_at=timezone.now() - timedelta(minutes=30)
        )
        fourth = self._make_draft()
        with self.assertRaises(EditSessionResponseError):
            start_doctor_edit_session(
                medical_document_id=fourth.id, user=self.doctor, purpose="edit"
            )
        docs[0].refresh_from_db()
        self.assertEqual(docs[0].locked_by_user_id, self.doctor.id)
        self.assertIsNotNone(docs[0].edit_session_token)
        fourth.refresh_from_db()
        self.assertIsNone(fourth.locked_by_user_id)

    def test_external_upload_locks_do_not_count_toward_limit(self) -> None:
        for _ in range(5):
            qe = self._make_queue_entry(
                position_no=self._next_queue_position_no(),
                entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            )
            session = PatientFormSession.objects.create(
                queue_entry=qe,
                form_locale="de-DE",
                expires_at=timezone.now() + timedelta(hours=1),
                created_by_user=self.doctor,
            )
            intake = PatientIntakeForm.objects.create(
                queue_entry=qe,
                session=session,
                form_status=IntakeStatus.SUBMITTED,
                submitted_at=timezone.now(),
                signature_sha256="e" * 64,
            )
            MedicalDocument.objects.create(
                queue_entry=qe,
                intake_form=intake,
                source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD,
                status=MedicalDocStatus.DRAFT,
                current_version_no=0,
                created_by_user=self.doctor,
                locked_by_user=self.doctor,
                locked_at=timezone.now(),
            )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id), 0
        )
        for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS):
            doc = self._make_draft()
            start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )
