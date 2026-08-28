"""Service and API tests for doctor edit-session locking."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.core.exceptions import DomainError
from apps.medical.constants import DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS
from apps.medical.edit_session import (
    EditSessionResponseError,
    count_doctor_active_document_locks,
    start_doctor_edit_session,
)
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import MedicalDocStatus, MedicalDocument, DocVersionStatus, MedicalDocumentVersion
from apps.medical.tests.test_services_coverage import ServicesCoverageBase
from apps.operations.models import AuditEvent
from apps.reception.models import PatientFormSession, QueueEntryStatus
from apps.users.models import StaffUser
from django.test import Client


class EditSessionTestMixin:
    def _make_isolated_draft_doc(self) -> MedicalDocument:
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
            signature_sha256="c" * 64,
        )
        return MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )

    def _other_doctor(self, suffix: str = "sess") -> StaffUser:
        user = StaffUser.objects.create_user(
            username=f"cov-{suffix}",
            email=f"cov-{suffix}@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(user, "Doctor")
        return user


class StartDoctorEditSessionTests(EditSessionTestMixin, ServicesCoverageBase):
    def test_acquire_free_lock_issues_token(self) -> None:
        doc = self._make_isolated_draft_doc()
        result = start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="edit",
        )
        self.assertEqual(result.mode, "acquired")
        doc.refresh_from_db()
        self.assertEqual(doc.locked_by_user_id, self.doctor.id)
        self.assertEqual(doc.edit_session_token, result.edit_session_token)
        self.assertEqual(doc.edit_session_revision, 1)
        self.assertIsNone(doc.last_previewed_draft_revision)

    def test_resume_with_matching_token(self) -> None:
        doc = self._make_isolated_draft_doc()
        first = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        old_locked_at = MedicalDocument.objects.get(id=doc.id).locked_at
        resumed = start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="edit",
            edit_session_token=first.edit_session_token,
        )
        self.assertEqual(resumed.mode, "resumed")
        self.assertEqual(resumed.edit_session_token, first.edit_session_token)
        doc.refresh_from_db()
        self.assertGreater(doc.locked_at, old_locked_at)
        self.assertEqual(doc.edit_session_revision, first.edit_session_revision)

    def test_other_doctor_gets_423(self) -> None:
        doc = self._make_isolated_draft_doc()
        start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        other = self._other_doctor("sess-other")
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id, user=other, purpose="edit"
            )
        self.assertEqual(ctx.exception.error_key, "document_locked_by_other")
        self.assertEqual(ctx.exception.http_status, 423)

    def test_reclaim_requires_confirmation(self) -> None:
        doc = self._make_isolated_draft_doc()
        start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id,
                user=self.doctor,
                purpose="edit",
            )
        self.assertEqual(
            ctx.exception.error_key, "edit_session_reclaim_confirmation_required"
        )
        self.assertIn("edit_session_revision", ctx.exception.payload)

    def test_reclaim_after_confirmation_rotates_token(self) -> None:
        doc = self._make_isolated_draft_doc()
        first = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id,
                user=self.doctor,
                purpose="edit",
            )
        reclaimed = start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="edit",
            reclaim_confirmed=True,
            expected_edit_session_revision=int(
                ctx.exception.payload["edit_session_revision"]
            ),
            edit_session_request_id=uuid.uuid4(),
        )
        self.assertEqual(reclaimed.mode, "reclaimed")
        self.assertNotEqual(reclaimed.edit_session_token, first.edit_session_token)
        self.assertGreater(reclaimed.edit_session_revision, first.edit_session_revision)

    def test_reclaim_idempotent_by_request_id(self) -> None:
        doc = self._make_isolated_draft_doc()
        start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        request_id = uuid.uuid4()
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id,
                user=self.doctor,
                purpose="edit",
            )
        reclaimed = start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="edit",
            reclaim_confirmed=True,
            expected_edit_session_revision=int(
                ctx.exception.payload["edit_session_revision"]
            ),
            edit_session_request_id=request_id,
        )
        replay = start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="edit",
            edit_session_request_id=request_id,
        )
        self.assertEqual(replay.edit_session_token, reclaimed.edit_session_token)
        doc.refresh_from_db()
        self.assertEqual(doc.edit_session_revision, reclaimed.edit_session_revision)

    def test_doctor_lock_limit_blocks_fourth_document(self) -> None:
        docs = [
            self._make_isolated_draft_doc()
            for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS)
        ]
        for doc in docs:
            start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
        fourth = self._make_isolated_draft_doc()
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=fourth.id, user=self.doctor, purpose="edit"
            )
        self.assertEqual(ctx.exception.error_key, "doctor_lock_limit_reached")
        self.assertEqual(
            len(ctx.exception.payload.get("locked_documents", [])),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )

    def test_resume_does_not_consume_extra_lock_slot(self) -> None:
        docs = [
            self._make_isolated_draft_doc()
            for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS)
        ]
        tokens = []
        for doc in docs:
            result = start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
            tokens.append(result.edit_session_token)
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )
        resumed = start_doctor_edit_session(
            medical_document_id=docs[0].id,
            user=self.doctor,
            purpose="edit",
            edit_session_token=tokens[0],
        )
        self.assertEqual(resumed.mode, "resumed")
        self.assertEqual(
            count_doctor_active_document_locks(user_id=self.doctor.id),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )

    def _make_published_doc(self) -> MedicalDocument:
        doc = self._make_isolated_draft_doc()
        doc.status = MedicalDocStatus.PUBLISHED
        doc.save(update_fields=["status", "updated_at"])
        self._make_published_version(doc, version_no=1, published_by_user=self.doctor)
        doc.refresh_from_db()
        return doc

    def test_amend_purpose_creates_pending_revision_and_lock(self) -> None:
        doc = self._make_published_doc()
        result = start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="amend",
        )
        doc.refresh_from_db()
        self.assertEqual(result.mode, "acquired")
        self.assertTrue(doc.has_pending_revision)
        self.assertEqual(doc.draft_revision, 1)
        self.assertEqual(doc.locked_by_user_id, self.doctor.id)
        self.assertIsNotNone(doc.edit_session_token)
        pending = MedicalDocumentVersion.objects.get(
            medical_document_id=doc.id,
            version_status=DocVersionStatus.DRAFT,
        )
        self.assertEqual(pending.version_no, 2)
        published = MedicalDocumentVersion.objects.get(
            medical_document_id=doc.id,
            version_no=1,
            version_status=DocVersionStatus.PUBLISHED,
        )
        self.assertEqual(
            pending.medical_payload,
            published.medical_payload,
        )

    def test_amend_purpose_rejects_non_publisher(self) -> None:
        doc = self._make_published_doc()
        other = self._other_doctor("amend-np")
        with self.assertRaises(DomainError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id,
                user=other,
                purpose="amend",
            )
        self.assertEqual(
            ctx.exception.api_message_key,
            "other.domain.amend_publisher_only",
        )
        doc.refresh_from_db()
        self.assertFalse(doc.has_pending_revision)

    def test_amend_purpose_rejects_when_revision_already_open(self) -> None:
        doc = self._make_published_doc()
        start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="amend",
        )
        doc.refresh_from_db()
        with self.assertRaises(DomainError):
            start_doctor_edit_session(
                medical_document_id=doc.id,
                user=self.doctor,
                purpose="amend",
            )

    def test_acquire_emits_audit_event(self) -> None:
        doc = self._make_isolated_draft_doc()
        before = AuditEvent.objects.filter(
            medical_document_id=doc.id,
            event_type="DOCUMENT_LOCK_ACQUIRED",
        ).count()
        start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        after = AuditEvent.objects.filter(
            medical_document_id=doc.id,
            event_type="DOCUMENT_LOCK_ACQUIRED",
        ).count()
        self.assertEqual(after, before + 1)


class EditSessionApiTests(EditSessionTestMixin, ServicesCoverageBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.doctor)
        self.doc = self._make_isolated_draft_doc()

    def test_post_edit_session_returns_token(self) -> None:
        response = self.client.post(
            f"/api/v1/medical-documents/{self.doc.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], "acquired")
        self.assertIn("edit_session_token", body)
        self.assertIn("draft_revision", body)

    def test_post_edit_session_reclaim_confirmation_409(self) -> None:
        first = self.client.post(
            f"/api/v1/medical-documents/{self.doc.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            f"/api/v1/medical-documents/{self.doc.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            second.json().get("error_key"),
            "edit_session_reclaim_confirmation_required",
        )

    def test_admin_cannot_start_edit_session(self) -> None:
        admin = StaffUser.objects.create_user(
            username="sess-admin",
            email="sess-admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(admin, "Admin")
        client = Client()
        client.force_login(admin)
        response = client.post(
            f"/api/v1/medical-documents/{self.doc.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
