"""Tests for doctor Befund write gate (token, draft_revision, idempotency)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import Client
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.constants import DOCUMENT_LOCK_TIMEOUT_HOURS
from apps.medical.edit_session import EditSessionResponseError, start_doctor_edit_session
from apps.medical.models import MedicalDocStatus, MedicalDocument, MedicalDocumentVersion
from apps.medical.tests.test_services_coverage import ServicesCoverageBase
from apps.medical.write_gate import (
    mark_doctor_draft_previewed,
    mutate_doctor_publish,
    mutate_doctor_save_draft,
)
from apps.reception.models import PatientFormSession, QueueEntryStatus
from apps.users.models import StaffUser


class WriteGateServiceTests(ServicesCoverageBase):
    def _make_locked_draft(self) -> tuple[MedicalDocument, dict]:
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
            signature_sha256="d" * 64,
        )
        doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        result = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        return doc, {
            "edit_session_token": result.edit_session_token,
            "draft_revision": result.draft_revision,
        }

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

    def test_save_draft_increments_revision_and_replays_same_request_id(self) -> None:
        doc, sess = self._make_locked_draft()
        request_id = uuid.uuid4()
        first = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess["edit_session_token"],
            expected_draft_revision=0,
            draft_save_request_id=request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="a"),
        )
        self.assertFalse(first.replayed)
        self.assertEqual(first.draft_revision, 1)

        replay = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess["edit_session_token"],
            expected_draft_revision=0,
            draft_save_request_id=request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="ignored"),
        )
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.draft_revision, 1)
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, 1)
        self.assertEqual(doc.versions.count(), 1)

    def test_same_request_id_with_other_base_revision_conflicts(self) -> None:
        doc, sess = self._make_locked_draft()
        request_id = uuid.uuid4()
        mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess["edit_session_token"],
            expected_draft_revision=0,
            draft_save_request_id=request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(),
        )
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess["edit_session_token"],
                expected_draft_revision=1,
                draft_save_request_id=request_id,
                medical_payload_schema_version=1,
                medical_payload=self._payload(note="b"),
            )
        self.assertEqual(ctx.exception.error_key, "draft_request_id_reused")

    def test_stale_expected_revision_conflicts(self) -> None:
        doc, sess = self._make_locked_draft()
        mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess["edit_session_token"],
            expected_draft_revision=0,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=self._payload(),
        )
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess["edit_session_token"],
                expected_draft_revision=0,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(note="late"),
            )
        self.assertEqual(ctx.exception.error_key, "draft_revision_conflict")

    def test_stale_token_returns_edit_session_stale(self) -> None:
        doc, sess = self._make_locked_draft()
        start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="edit",
            reclaim_confirmed=True,
            expected_edit_session_revision=1,
            edit_session_request_id=uuid.uuid4(),
        )
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess["edit_session_token"],
                expected_draft_revision=0,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(),
            )
        self.assertEqual(ctx.exception.error_key, "edit_session_stale")

    def test_expired_lock_returns_edit_session_expired(self) -> None:
        doc, sess = self._make_locked_draft()
        MedicalDocument.objects.filter(pk=doc.pk).update(
            locked_at=timezone.now()
            - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS + 1)
        )
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess["edit_session_token"],
                expected_draft_revision=0,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(),
            )
        self.assertEqual(ctx.exception.error_key, "edit_session_expired")

    def test_publish_requires_matching_preview_revision(self) -> None:
        doc, sess = self._make_locked_draft()
        saved = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess["edit_session_token"],
            expected_draft_revision=0,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=self._payload(),
        )
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_publish(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess["edit_session_token"],
                expected_draft_revision=saved.draft_revision,
                publish_request_id=uuid.uuid4(),
                publish_locale="de-DE",
            )
        self.assertEqual(ctx.exception.error_key, "publish_preview_revision_stale")

        mark_doctor_draft_previewed(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess["edit_session_token"],
            expected_draft_revision=saved.draft_revision,
        )
        published = mutate_doctor_publish(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess["edit_session_token"],
            expected_draft_revision=saved.draft_revision,
            publish_request_id=uuid.uuid4(),
            publish_locale="de-DE",
        )
        self.assertEqual(published.version_status, "PUBLISHED")
        doc.refresh_from_db()
        self.assertIsNone(doc.edit_session_token)
        self.assertIsNone(doc.locked_by_user_id)


class WriteGateApiTests(WriteGateServiceTests):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.doctor)

    def test_put_draft_and_publish_via_api(self) -> None:
        qe = self._make_queue_entry(
            position_no=self._next_queue_position_no(),
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        )
        session_row = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=session_row,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="e" * 64,
        )
        doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        mid = str(doc.id)
        session_resp = self.client.post(
            f"/api/v1/medical-documents/{mid}/edit-session",
            data={"purpose": "edit"},
            content_type="application/json",
        )
        self.assertEqual(session_resp.status_code, 200, session_resp.content)
        sess = session_resp.json()
        draft = self.client.put(
            f"/api/v1/medical-documents/{mid}/draft",
            data={
                "medical_payload_schema_version": 1,
                "medical_payload": self._payload(),
                "edit_session_token": sess["edit_session_token"],
                "expected_draft_revision": sess["draft_revision"],
                "draft_save_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(draft.status_code, 200, draft.content)
        rev = draft.json()["draft_revision"]
        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            return_value=(b"%PDF-1.4", None),
        ):
            preview = self.client.get(
                f"/api/v1/medical-documents/{mid}/preview-pdf"
                f"?source=draft&expected_draft_revision={rev}",
                HTTP_X_EDIT_SESSION_TOKEN=sess["edit_session_token"],
            )
        self.assertEqual(preview.status_code, 200, preview.content)
        publish = self.client.post(
            f"/api/v1/medical-documents/{mid}/publish",
            data={
                "publish_request_id": str(uuid.uuid4()),
                "publish_locale": "de-DE",
                "edit_session_token": sess["edit_session_token"],
                "expected_draft_revision": rev,
            },
            content_type="application/json",
        )
        self.assertEqual(publish.status_code, 200, publish.content)

    def test_admin_cannot_put_draft(self) -> None:
        doc, sess = self._make_locked_draft()
        admin = StaffUser.objects.create_user(
            username="wg-admin",
            email="wg-admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(admin, "Admin")
        client = Client()
        client.force_login(admin)
        response = client.put(
            f"/api/v1/medical-documents/{doc.id}/draft",
            data={
                "medical_payload_schema_version": 1,
                "medical_payload": self._payload(),
                "edit_session_token": str(sess["edit_session_token"]),
                "expected_draft_revision": 0,
                "draft_save_request_id": str(uuid.uuid4()),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
