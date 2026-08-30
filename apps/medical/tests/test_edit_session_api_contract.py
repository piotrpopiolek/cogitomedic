"""API contract: error_key grid, CSRF, Admin/Manager, EXTERNAL_UPLOAD, token secrecy."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from django.test import Client
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.constants import (
    DOCUMENT_LOCK_TIMEOUT_HOURS,
    DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
)
from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
)
from apps.medical.tests.test_services_coverage import ServicesCoverageBase
from apps.operations.models import AuditEvent
from apps.reception.models import PatientFormSession, QueueEntryStatus
from apps.users.models import StaffUser


class EditSessionApiContractTests(ServicesCoverageBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.doctor)

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
            signature_sha256="n" * 64,
        )
        return MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )

    def _start(self, doc: MedicalDocument) -> dict:
        resp = self.client.post(
            f"/api/v1/medical-documents/{doc.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def _other_doctor(self, suffix: str) -> StaffUser:
        user = StaffUser.objects.create_user(
            username=f"api-{suffix}",
            email=f"api-{suffix}@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(user, "Doctor")
        return user

    def _staff(self, role: str, suffix: str) -> StaffUser:
        user = StaffUser.objects.create_user(
            username=f"{role.lower()}-{suffix}",
            email=f"{role.lower()}-{suffix}@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(user, role)
        return user

    def test_error_key_document_locked_by_other(self) -> None:
        doc = self._make_draft()
        self._start(doc)
        other = self._other_doctor("lock")
        other_client = Client()
        other_client.force_login(other)
        resp = other_client.post(
            f"/api/v1/medical-documents/{doc.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 423)
        body = resp.json()
        self.assertEqual(body["error_key"], "document_locked_by_other")
        self.assertNotIn("edit_session_token", body)
        self.assertIn("locked_by_username", body)

    def test_error_key_reclaim_confirmation_and_superseded(self) -> None:
        doc = self._make_draft()
        first = self._start(doc)
        resp = self.client.post(
            f"/api/v1/medical-documents/{doc.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body["error_key"], "edit_session_reclaim_confirmation_required")
        self.assertNotIn("edit_session_token", body)
        rev = body["edit_session_revision"]
        reclaim = self.client.post(
            f"/api/v1/medical-documents/{doc.id}/edit-session",
            data={
                "purpose": "edit",
                "reclaim_confirmed": True,
                "expected_edit_session_revision": rev,
                "edit_session_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(reclaim.status_code, 200, reclaim.content)
        stale = self.client.post(
            f"/api/v1/medical-documents/{doc.id}/edit-session",
            data={
                "purpose": "edit",
                "reclaim_confirmed": True,
                "expected_edit_session_revision": rev,
                "edit_session_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error_key"], "reclaim_superseded")
        self.assertNotIn("edit_session_token", stale.json())
        self.assertNotIn(first["edit_session_token"], stale.content.decode())

    def test_error_key_draft_revision_conflict_and_request_id_reused(self) -> None:
        doc = self._make_draft()
        sess = self._start(doc)
        request_id = str(uuid.uuid4())
        first = self.client.put(
            f"/api/v1/medical-documents/{doc.id}/draft",
            data={
                "medical_payload_schema_version": 1,
                "medical_payload": self._payload(note="a"),
                "edit_session_token": sess["edit_session_token"],
                "expected_draft_revision": sess["draft_revision"],
                "draft_save_request_id": request_id,
            },
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200, first.content)
        conflict = self.client.put(
            f"/api/v1/medical-documents/{doc.id}/draft",
            data={
                "medical_payload_schema_version": 1,
                "medical_payload": self._payload(note="b"),
                "edit_session_token": sess["edit_session_token"],
                "expected_draft_revision": sess["draft_revision"],
                "draft_save_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error_key"], "draft_revision_conflict")
        self.assertNotIn("edit_session_token", conflict.json())

        reused = self.client.put(
            f"/api/v1/medical-documents/{doc.id}/draft",
            data={
                "medical_payload_schema_version": 1,
                "medical_payload": self._payload(note="c"),
                "edit_session_token": sess["edit_session_token"],
                "expected_draft_revision": first.json()["draft_revision"],
                "draft_save_request_id": request_id,
            },
            content_type="application/json",
        )
        self.assertEqual(reused.status_code, 409)
        self.assertEqual(reused.json()["error_key"], "draft_request_id_reused")

    def test_error_key_edit_session_stale_and_expired(self) -> None:
        doc = self._make_draft()
        sess = self._start(doc)
        self.client.post(
            f"/api/v1/medical-documents/{doc.id}/edit-session",
            data={
                "purpose": "edit",
                "reclaim_confirmed": True,
                "expected_edit_session_revision": sess["edit_session_revision"],
                "edit_session_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        stale = self.client.put(
            f"/api/v1/medical-documents/{doc.id}/draft",
            data={
                "medical_payload_schema_version": 1,
                "medical_payload": self._payload(),
                "edit_session_token": sess["edit_session_token"],
                "expected_draft_revision": 0,
                "draft_save_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 423)
        self.assertEqual(stale.json()["error_key"], "edit_session_stale")

        doc2 = self._make_draft()
        sess2 = self._start(doc2)
        MedicalDocument.objects.filter(id=doc2.id).update(
            locked_at=timezone.now()
            - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS + 1)
        )
        expired = self.client.put(
            f"/api/v1/medical-documents/{doc2.id}/draft",
            data={
                "medical_payload_schema_version": 1,
                "medical_payload": self._payload(),
                "edit_session_token": sess2["edit_session_token"],
                "expected_draft_revision": 0,
                "draft_save_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(expired.status_code, 423)
        self.assertEqual(expired.json()["error_key"], "edit_session_expired")

    def test_error_key_doctor_lock_limit_reached_payload(self) -> None:
        for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS):
            self._start(self._make_draft())
        fourth = self._make_draft()
        resp = self.client.post(
            f"/api/v1/medical-documents/{fourth.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body["error_key"], "doctor_lock_limit_reached")
        self.assertEqual(len(body["locked_documents"]), DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS)
        self.assertNotIn("edit_session_token", body)
        self.assertNotIn("edit_session_token", json.dumps(body))
        fourth.refresh_from_db()
        self.assertIsNone(fourth.locked_by_user_id)

    def test_error_key_publish_preview_revision_stale(self) -> None:
        doc = self._make_draft()
        sess = self._start(doc)
        draft = self.client.put(
            f"/api/v1/medical-documents/{doc.id}/draft",
            data={
                "medical_payload_schema_version": 1,
                "medical_payload": self._payload(),
                "edit_session_token": sess["edit_session_token"],
                "expected_draft_revision": 0,
                "draft_save_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(draft.status_code, 200, draft.content)
        rev = draft.json()["draft_revision"]
        pub = self.client.post(
            f"/api/v1/medical-documents/{doc.id}/publish",
            data={
                "publish_request_id": str(uuid.uuid4()),
                "publish_locale": "de-DE",
                "edit_session_token": sess["edit_session_token"],
                "expected_draft_revision": rev,
            },
            content_type="application/json",
        )
        self.assertEqual(pub.status_code, 409)
        self.assertEqual(pub.json()["error_key"], "publish_preview_revision_stale")
        self.assertNotIn("edit_session_token", pub.json())

    def test_unlock_gone_and_missing_document(self) -> None:
        doc = self._make_draft()
        unlock = self.client.post(f"/api/v1/medical-documents/{doc.id}/unlock")
        self.assertEqual(unlock.status_code, 410)
        self.assertEqual(unlock.json()["error_key"], "other.api.unlock_gone")
        missing = self.client.post(
            f"/api/v1/medical-documents/{uuid.uuid4()}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 404)

    def test_csrf_required_for_edit_session_mutation(self) -> None:
        doc = self._make_draft()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.doctor)
        resp = csrf_client.post(
            f"/api/v1/medical-documents/{doc.id}/edit-session",
            data=json.dumps({"purpose": "edit"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        doc.refresh_from_db()
        self.assertIsNone(doc.locked_by_user_id)

    def test_admin_and_manager_mutations_have_no_side_effects(self) -> None:
        doc = self._make_draft()
        before_token = None
        for role in ("Admin", "Manager"):
            user = self._staff(role, uuid.uuid4().hex[:6])
            client = Client()
            client.force_login(user)
            for method, path, payload in (
                (
                    "post",
                    f"/api/v1/medical-documents/{doc.id}/edit-session",
                    {"purpose": "edit"},
                ),
                (
                    "put",
                    f"/api/v1/medical-documents/{doc.id}/draft",
                    {
                        "medical_payload_schema_version": 1,
                        "medical_payload": self._payload(),
                        "edit_session_token": str(uuid.uuid4()),
                        "expected_draft_revision": 0,
                        "draft_save_request_id": str(uuid.uuid4()),
                    },
                ),
                (
                    "post",
                    f"/api/v1/medical-documents/{doc.id}/publish",
                    {
                        "publish_request_id": str(uuid.uuid4()),
                        "publish_locale": "de-DE",
                        "edit_session_token": str(uuid.uuid4()),
                        "expected_draft_revision": 0,
                    },
                ),
                (
                    "post",
                    f"/api/v1/medical-documents/{doc.id}/discard-revision",
                    {
                        "edit_session_token": str(uuid.uuid4()),
                        "expected_draft_revision": 0,
                    },
                ),
            ):
                resp = getattr(client, method)(
                    path, data=payload, content_type="application/json"
                )
                self.assertIn(resp.status_code, (403, 405), msg=f"{role} {path}")
                self.assertNotIn("edit_session_token", resp.json())
            doc.refresh_from_db()
            self.assertIsNone(doc.locked_by_user_id)
            self.assertEqual(doc.edit_session_token, before_token)
            self.assertEqual(doc.draft_revision, 0)

    def test_token_only_on_edit_session_success_and_anonymized_in_audit(self) -> None:
        doc = self._make_draft()
        first = self._start(doc)
        token = first["edit_session_token"]
        reclaim = self.client.post(
            f"/api/v1/medical-documents/{doc.id}/edit-session",
            data={
                "purpose": "edit",
                "reclaim_confirmed": True,
                "expected_edit_session_revision": first["edit_session_revision"],
                "edit_session_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(reclaim.status_code, 200)
        events = AuditEvent.objects.filter(
            medical_document_id=doc.id,
            event_type="DOCUMENT_LOCK_RECLAIMED",
        )
        self.assertEqual(events.count(), 1)
        meta = events.first().metadata or {}
        dumped = json.dumps(meta)
        self.assertNotIn(token, dumped)
        self.assertIn("previous_token_prefix", meta)
        self.assertEqual(meta["previous_token_prefix"], token[:8])
        self.assertNotEqual(meta["previous_token_prefix"], token)

    def test_external_upload_rejects_edit_session_without_token_or_limit(self) -> None:
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
            signature_sha256="x" * 64,
        )
        ext = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        resp = self.client.post(
            f"/api/v1/medical-documents/{ext.id}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertNotIn("edit_session_token", body)
        for _ in range(DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS):
            self._start(self._make_draft())
        self.assertEqual(
            MedicalDocument.objects.filter(
                locked_by_user_id=self.doctor.id,
                source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            ).count(),
            DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
        )
