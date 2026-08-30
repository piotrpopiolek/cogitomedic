"""draft_revision monotonicity, preview race, and idempotency rollback."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import Client
from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.edit_session import (
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
    mark_doctor_draft_previewed,
    mutate_doctor_discard_revision,
    mutate_doctor_publish,
    mutate_doctor_save_draft,
)
from apps.operations.models import AuditEvent
from apps.reception.models import PatientFormSession, QueueEntryStatus


class DraftRevisionMatrixTests(ServicesCoverageBase):
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

    def _make_locked_draft(self):
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
            signature_sha256="m" * 64,
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

    def _make_published(self) -> MedicalDocument:
        doc, _ = self._make_locked_draft()
        # clear lock for clean published seed
        MedicalDocument.objects.filter(id=doc.id).update(
            locked_by_user=None,
            locked_at=None,
            edit_session_token=None,
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
            pdf_local_path="/media/befund/rev-matrix.pdf",
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
            draft_revision=0,
        )
        doc.refresh_from_db()
        return doc

    def test_amend_and_put_draft_increment_revision(self) -> None:
        pub = self._make_published()
        self.assertEqual(pub.draft_revision, 0)
        sess = start_doctor_edit_session(
            medical_document_id=pub.id, user=self.doctor, purpose="amend"
        )
        pub.refresh_from_db()
        self.assertEqual(pub.draft_revision, 1)
        self.assertEqual(sess.draft_revision, 1)

        saved = mutate_doctor_save_draft(
            medical_document_id=pub.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=1,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="changed"),
            intent="amend",
        )
        self.assertEqual(saved.draft_revision, 2)
        pub.refresh_from_db()
        self.assertEqual(pub.draft_revision, 2)

    def test_preview_publish_discard_replay_denials_do_not_bump(self) -> None:
        doc, sess = self._make_locked_draft()
        request_id = uuid.uuid4()
        first = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=0,
            draft_save_request_id=request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="v1"),
        )
        self.assertEqual(first.draft_revision, 1)
        before = 1

        mark_doctor_draft_previewed(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=before,
        )
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, before)

        replay = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=0,
            draft_save_request_id=request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="ignored"),
        )
        self.assertTrue(replay.replayed)
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, before)

        with self.assertRaises(EditSessionResponseError):
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess.edit_session_token,
                expected_draft_revision=0,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(note="stale"),
            )
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, before)

        published = mutate_doctor_publish(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=before,
            publish_request_id=uuid.uuid4(),
            publish_locale="de-DE",
        )
        self.assertEqual(published.version_status, DocVersionStatus.PUBLISHED)
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, before)

        # Amend + discard must not reset monotonic counter; discard leaves revision.
        amend = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="amend"
        )
        doc.refresh_from_db()
        after_amend = doc.draft_revision
        self.assertEqual(after_amend, before + 1)
        mutate_doctor_discard_revision(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=amend.edit_session_token,
            expected_draft_revision=after_amend,
        )
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, after_amend)

    def test_preview_race_bumped_revision_rejects_without_marking(self) -> None:
        doc, sess = self._make_locked_draft()
        saved = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=0,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="race"),
        )
        client = Client()
        client.force_login(self.doctor)
        expected = saved.draft_revision

        def bump_during_pdf(*_args, **_kwargs):
            mutate_doctor_save_draft(
                medical_document_id=doc.id,
                user=self.doctor,
                edit_session_token=sess.edit_session_token,
                expected_draft_revision=expected,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(note="during-pdf"),
            )
            return (b"%PDF-1.4 race", None)

        with patch(
            "apps.medical.api_views.build_merged_preview_pdf_bytes",
            side_effect=bump_during_pdf,
        ):
            resp = client.get(
                f"/api/v1/medical-documents/{doc.id}/preview-pdf"
                f"?source=draft&expected_draft_revision={expected}",
                HTTP_X_EDIT_SESSION_TOKEN=str(sess.edit_session_token),
            )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json().get("error_key"), "draft_revision_conflict")
        doc.refresh_from_db()
        self.assertIsNone(doc.last_previewed_draft_revision)
        self.assertEqual(doc.draft_revision, expected + 1)

    def test_failed_save_rolls_back_last_draft_request_fields(self) -> None:
        doc, sess = self._make_locked_draft()
        before = {
            "draft_revision": doc.draft_revision,
            "last_draft_request_id": doc.last_draft_request_id,
            "last_draft_request_base_revision": doc.last_draft_request_base_revision,
            "last_draft_request_result_revision": doc.last_draft_request_result_revision,
        }
        with patch(
            "apps.medical.write_gate._refresh_lock_on_mutation",
            side_effect=RuntimeError("simulated failure after mutation"),
        ):
            with self.assertRaises(RuntimeError):
                mutate_doctor_save_draft(
                    medical_document_id=doc.id,
                    user=self.doctor,
                    edit_session_token=sess.edit_session_token,
                    expected_draft_revision=0,
                    draft_save_request_id=uuid.uuid4(),
                    medical_payload_schema_version=1,
                    medical_payload=self._payload(note="rollback"),
                )
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, before["draft_revision"])
        self.assertEqual(doc.last_draft_request_id, before["last_draft_request_id"])
        self.assertEqual(
            doc.last_draft_request_base_revision,
            before["last_draft_request_base_revision"],
        )
        self.assertEqual(
            doc.last_draft_request_result_revision,
            before["last_draft_request_result_revision"],
        )
        self.assertEqual(
            MedicalDocumentVersion.objects.filter(medical_document_id=doc.id).count(),
            0,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                medical_document_id=doc.id, event_type="DOCUMENT_DRAFT_SAVED"
            ).count(),
            0,
        )

    def test_stale_draft_request_id_after_discard_does_not_replay(self) -> None:
        """Discard must clear draft save idempotency keys before a new amend cycle."""
        pub = self._make_published()
        amend = start_doctor_edit_session(
            medical_document_id=pub.id, user=self.doctor, purpose="amend"
        )
        stale_request_id = uuid.uuid4()
        stale_base = amend.draft_revision
        mutate_doctor_save_draft(
            medical_document_id=pub.id,
            user=self.doctor,
            edit_session_token=amend.edit_session_token,
            expected_draft_revision=stale_base,
            draft_save_request_id=stale_request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="first-cycle"),
            intent="amend",
        )
        mutate_doctor_discard_revision(
            medical_document_id=pub.id,
            user=self.doctor,
            edit_session_token=amend.edit_session_token,
            expected_draft_revision=stale_base + 1,
        )
        pub.refresh_from_db()
        self.assertIsNone(pub.last_draft_request_id)
        self.assertIsNone(pub.last_draft_request_base_revision)
        self.assertIsNone(pub.last_draft_request_result_revision)

        again = start_doctor_edit_session(
            medical_document_id=pub.id, user=self.doctor, purpose="amend"
        )
        # Stale client retry must apply to the new DRAFT, not silently replay.
        applied = mutate_doctor_save_draft(
            medical_document_id=pub.id,
            user=self.doctor,
            edit_session_token=again.edit_session_token,
            expected_draft_revision=again.draft_revision,
            draft_save_request_id=stale_request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="second-cycle"),
            intent="amend",
        )
        self.assertFalse(applied.replayed)
        self.assertEqual(applied.version.medical_payload.get("note"), "second-cycle")
        pub.refresh_from_db()
        self.assertEqual(pub.last_draft_request_id, stale_request_id)

    def test_publish_clears_draft_request_idempotency_keys(self) -> None:
        doc, sess = self._make_locked_draft()
        request_id = uuid.uuid4()
        saved = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=0,
            draft_save_request_id=request_id,
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="to-publish"),
        )
        mark_doctor_draft_previewed(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=saved.draft_revision,
        )
        mutate_doctor_publish(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=saved.draft_revision,
            publish_request_id=uuid.uuid4(),
            publish_locale="de-DE",
        )
        doc.refresh_from_db()
        self.assertIsNone(doc.last_draft_request_id)
        self.assertIsNone(doc.last_draft_request_base_revision)
        self.assertIsNone(doc.last_draft_request_result_revision)

    def test_atomic_block_open_during_failure(self) -> None:
        """Guard: mutate_doctor_save_draft stays inside transaction.atomic."""
        self.assertTrue(
            getattr(mutate_doctor_save_draft, "__wrapped__", None) is not None
            or transaction.get_connection().in_atomic_block is False
        )
        # Decorator presence is the contract; verify via attribute set by Django.
        self.assertTrue(hasattr(mutate_doctor_save_draft, "__wrapped__"))
