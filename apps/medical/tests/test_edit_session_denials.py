"""Denial side-effect matrix, revoke guard, and write-gate architecture checks."""

from __future__ import annotations

import ast
import uuid
from datetime import timedelta
from pathlib import Path
from django.test import Client
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.constants import DOCUMENT_LOCK_TIMEOUT_HOURS
from apps.medical.edit_session import (
    DoctorEditSessionResult,
    EditSessionResponseError,
    start_doctor_edit_session,
)
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.medical.tests.test_services_coverage import ServicesCoverageBase
from apps.medical.write_gate import (
    assert_no_revision_in_progress_for_revoke,
    mutate_doctor_publish,
    mutate_doctor_save_draft,
)
from apps.operations.models import AuditEvent
from apps.reception.models import PatientFormSession, QueueEntryStatus
from apps.users.models import StaffUser


class _DenialMatrixMixin(ServicesCoverageBase):
    def _make_locked_draft(self) -> tuple[MedicalDocument, DoctorEditSessionResult]:
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
            signature_sha256="f" * 64,
        )
        doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        sess = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        return doc, sess

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

    def _other_doctor(self, suffix: str) -> StaffUser:
        user = StaffUser.objects.create_user(
            username=f"deny-{suffix}",
            email=f"deny-{suffix}@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(user, "Doctor")
        return user

    def _snapshot(self, doc: MedicalDocument) -> dict:
        doc.refresh_from_db()
        version = (
            MedicalDocumentVersion.objects.filter(medical_document_id=doc.id)
            .order_by("-version_no")
            .first()
        )
        return {
            "draft_revision": doc.draft_revision,
            "edit_session_revision": doc.edit_session_revision,
            "edit_session_token": doc.edit_session_token,
            "locked_by_user_id": doc.locked_by_user_id,
            "locked_at": doc.locked_at,
            "last_previewed_draft_revision": doc.last_previewed_draft_revision,
            "last_draft_request_id": doc.last_draft_request_id,
            "last_edit_session_request_id": doc.last_edit_session_request_id,
            "status": doc.status,
            "has_pending_revision": doc.has_pending_revision,
            "updated_at": doc.updated_at,
            "version_count": MedicalDocumentVersion.objects.filter(
                medical_document_id=doc.id
            ).count(),
            "version_payload": None if version is None else version.medical_payload,
            "audit_count": AuditEvent.objects.filter(
                medical_document_id=doc.id
            ).count(),
        }

    def _assert_unchanged(self, doc: MedicalDocument, before: dict) -> None:
        self.assertEqual(self._snapshot(doc), before)


class EditSessionDenialSideEffectTests(_DenialMatrixMixin):
    def test_other_doctor_acquire_has_no_side_effects(self) -> None:
        doc, _sess = self._make_locked_draft()
        before = self._snapshot(doc)
        other = self._other_doctor("other-acq")
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id, user=other, purpose="edit"
            )
        self.assertEqual(ctx.exception.error_key, "document_locked_by_other")
        self._assert_unchanged(doc, before)

    def test_reclaim_without_confirm_has_no_side_effects(self) -> None:
        doc, _sess = self._make_locked_draft()
        before = self._snapshot(doc)
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id, user=self.doctor, purpose="edit"
            )
        self.assertEqual(
            ctx.exception.error_key, "edit_session_reclaim_confirmation_required"
        )
        self._assert_unchanged(doc, before)

    def test_reclaim_superseded_has_no_side_effects(self) -> None:
        doc, first = self._make_locked_draft()
        start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="edit",
            reclaim_confirmed=True,
            expected_edit_session_revision=first.edit_session_revision,
            edit_session_request_id=uuid.uuid4(),
        )
        before = self._snapshot(doc)
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=doc.id,
                user=self.doctor,
                purpose="edit",
                reclaim_confirmed=True,
                expected_edit_session_revision=first.edit_session_revision,
                edit_session_request_id=uuid.uuid4(),
            )
        self.assertEqual(ctx.exception.error_key, "reclaim_superseded")
        self._assert_unchanged(doc, before)

    def test_lock_limit_denial_has_no_side_effects(self) -> None:
        held = []
        for _ in range(3):
            held.append(self._make_locked_draft()[0])
        fourth_qe = self._make_queue_entry(
            position_no=self._next_queue_position_no(),
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        )
        session = PatientFormSession.objects.create(
            queue_entry=fourth_qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=fourth_qe,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="g" * 64,
        )
        fourth = MedicalDocument.objects.create(
            queue_entry=fourth_qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        before_held = [self._snapshot(doc) for doc in held]
        before_fourth = self._snapshot(fourth)
        with self.assertRaises(EditSessionResponseError) as ctx:
            start_doctor_edit_session(
                medical_document_id=fourth.id, user=self.doctor, purpose="edit"
            )
        self.assertEqual(ctx.exception.error_key, "doctor_lock_limit_reached")
        for doc, snap in zip(held, before_held, strict=True):
            self._assert_unchanged(doc, snap)
        self._assert_unchanged(fourth, before_fourth)

    def test_stale_token_save_has_no_side_effects(self) -> None:
        doc, sess = self._make_locked_draft()
        start_doctor_edit_session(
            medical_document_id=doc.id,
            user=self.doctor,
            purpose="edit",
            reclaim_confirmed=True,
            expected_edit_session_revision=sess.edit_session_revision,
            edit_session_request_id=uuid.uuid4(),
        )
        before = self._snapshot(doc)
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess.edit_session_token,
                expected_draft_revision=sess.draft_revision,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(summary_text="stale"),
            )
        self.assertEqual(ctx.exception.error_key, "edit_session_stale")
        self._assert_unchanged(doc, before)

    def test_expired_lock_save_has_no_side_effects(self) -> None:
        doc, sess = self._make_locked_draft()
        MedicalDocument.objects.filter(pk=doc.pk).update(
            locked_at=timezone.now()
            - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS + 1)
        )
        before = self._snapshot(doc)
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess.edit_session_token,
                expected_draft_revision=sess.draft_revision,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(summary_text="expired"),
            )
        self.assertEqual(ctx.exception.error_key, "edit_session_expired")
        self._assert_unchanged(doc, before)

    def test_draft_revision_conflict_has_no_side_effects(self) -> None:
        doc, sess = self._make_locked_draft()
        mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=sess.draft_revision,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=self._payload(summary_text="first"),
        )
        before = self._snapshot(doc)
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess.edit_session_token,
                expected_draft_revision=sess.draft_revision,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(summary_text="late"),
            )
        self.assertEqual(ctx.exception.error_key, "draft_revision_conflict")
        self._assert_unchanged(doc, before)

    def test_draft_request_id_reused_has_no_side_effects(self) -> None:
        doc, sess = self._make_locked_draft()
        request_id = uuid.uuid4()
        mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=sess.draft_revision,
            draft_save_request_id=request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(summary_text="a"),
        )
        before = self._snapshot(doc)
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess.edit_session_token,
                expected_draft_revision=before["draft_revision"],
                draft_save_request_id=request_id,
                medical_payload_schema_version=1,
                medical_payload=self._payload(summary_text="b"),
            )
        self.assertEqual(ctx.exception.error_key, "draft_request_id_reused")
        self._assert_unchanged(doc, before)

    def test_publish_preview_stale_has_no_side_effects(self) -> None:
        doc, sess = self._make_locked_draft()
        saved = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=sess.draft_revision,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=self._payload(summary_text="pub"),
        )
        before = self._snapshot(doc)
        with self.assertRaises(EditSessionResponseError) as ctx:
            mutate_doctor_publish(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess.edit_session_token,
                expected_draft_revision=saved.draft_revision,
                publish_request_id=uuid.uuid4(),
                publish_locale="de-DE",
            )
        self.assertEqual(ctx.exception.error_key, "publish_preview_revision_stale")
        self._assert_unchanged(doc, before)


class RevokeRevisionInProgressTests(_DenialMatrixMixin):
    def _make_published_with_delivery(self) -> MedicalDocument:
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
            signature_sha256="h" * 64,
        )
        doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            published_version_no=1,
            created_by_user=self.doctor,
            has_pending_revision=False,
        )
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
            published_by_user=self.doctor,
            publish_request_id=uuid.uuid4(),
            pdf_local_path="/media/befund/revoke-guard.pdf",
            hidrive_sent=True,
            hidrive_sent_at=now,
            sms_sent=True,
            sms_sent_at=now,
        )
        return doc

    def test_assert_blocks_when_pending_revision(self) -> None:
        doc = self._make_published_with_delivery()
        start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="amend"
        )
        doc.refresh_from_db()
        before = self._snapshot(doc)
        with self.assertRaises(EditSessionResponseError) as ctx:
            assert_no_revision_in_progress_for_revoke(doc)
        self.assertEqual(ctx.exception.error_key, "revision_in_progress")
        self._assert_unchanged(doc, before)

    def test_api_revoke_returns_409_while_revision_in_progress(self) -> None:
        pub = self._make_published_with_delivery()
        start_doctor_edit_session(
            medical_document_id=pub.id, user=self.doctor, purpose="amend"
        )
        before = self._snapshot(pub)
        client = Client()
        client.force_login(self.doctor)
        resp = client.post(f"/api/v1/medical-documents/{pub.id}/revoke")
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body.get("error_key"), "revision_in_progress")
        self._assert_unchanged(pub, before)


class WriteGateArchitectureTests(ServicesCoverageBase):
    """§6.2: doctor Befund mutators in api_views go only through write_gate."""

    FORBIDDEN_MUTATORS = {
        "save_draft_document_version",
        "publish_document_version",
        "discard_pending_revision",
        "begin_pending_revision_from_published",
    }
    REQUIRED_WRITE_GATE = {
        "mutate_doctor_save_draft",
        "mutate_doctor_publish",
        "mutate_doctor_discard_revision",
    }

    def test_api_views_doctor_mutators_only_via_write_gate(self) -> None:
        path = Path(__file__).resolve().parents[1] / "api_views.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_from_services: set[str] = set()
        imported_from_write_gate: set[str] = set()
        called_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = {alias.name for alias in node.names}
                if mod.endswith("medical.services") or mod == "apps.medical.services":
                    imported_from_services |= names
                if mod.endswith("medical.write_gate") or mod == "apps.medical.write_gate":
                    imported_from_write_gate |= names
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called_names.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called_names.add(func.attr)

        for forbidden in self.FORBIDDEN_MUTATORS:
            self.assertNotIn(
                forbidden,
                imported_from_services,
                msg=f"{forbidden} must not be imported into api_views",
            )
            self.assertNotIn(
                forbidden,
                called_names,
                msg=f"{forbidden} must not be called from api_views",
            )

        for required in self.REQUIRED_WRITE_GATE:
            self.assertIn(required, imported_from_write_gate)
            self.assertIn(required, called_names)

        # EXTERNAL_UPLOAD path may still call dedicated services.
        self.assertIn("publish_external_upload_version", imported_from_services)
        self.assertIn("start_external_upload_revision", imported_from_services)
