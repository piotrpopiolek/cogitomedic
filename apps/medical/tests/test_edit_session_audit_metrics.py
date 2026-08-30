"""Audit/metrics regressions and publish↔outbox lock-order contract."""

from __future__ import annotations

import inspect
import threading
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.edit_session import DoctorEditSessionResult, start_doctor_edit_session
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
)
from apps.medical.services import get_document_lock_state, publish_document_version
from apps.medical.tests.test_services_coverage import ServicesCoverageBase
from apps.medical.write_gate import (
    mark_doctor_draft_previewed,
    mutate_doctor_publish,
    mutate_doctor_save_draft,
)
from apps.operations.models import AuditEvent
from apps.operations.prom_metrics import build_metrics_payload
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.services import process_outbox_events
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
from datetime import date


class EditSessionAuditMetricsTests(ServicesCoverageBase):
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
            signature_sha256="o" * 64,
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
        doc.refresh_from_db()
        return doc, sess

    def test_acquire_save_conflict_audit_counts_and_metadata(self) -> None:
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
            signature_sha256="p" * 64,
        )
        medical = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        before = AuditEvent.objects.filter(medical_document_id=medical.id).count()
        sess = start_doctor_edit_session(
            medical_document_id=medical.id, user=self.doctor, purpose="edit"
        )
        acquired = AuditEvent.objects.filter(
            medical_document_id=medical.id, event_type="DOCUMENT_LOCK_ACQUIRED"
        )
        self.assertEqual(acquired.count(), 1)
        meta = acquired.first().metadata or {}
        self.assertEqual(meta.get("mode"), "acquired")
        self.assertEqual(meta.get("draft_revision"), 0)
        self.assertNotIn("edit_session_token", meta)
        self.assertNotIn(str(sess.edit_session_token), str(meta))

        mutate_doctor_save_draft(
            medical_document_id=medical.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=0,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=self._payload(note="audit"),
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                medical_document_id=medical.id, event_type="DOCUMENT_DRAFT_SAVED"
            ).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                medical_document_id=medical.id,
                event_type="DOCUMENT_LOCK_REFRESHED_ON_SAVE",
            ).count(),
            1,
        )
        audits_before_conflict = AuditEvent.objects.filter(
            medical_document_id=medical.id
        ).count()
        with self.assertRaises(Exception):
            mutate_doctor_save_draft(
                medical_document_id=medical.id,
                user=self.doctor,
                edit_session_token=sess.edit_session_token,
                expected_draft_revision=0,
                draft_save_request_id=uuid.uuid4(),
                medical_payload_schema_version=1,
                medical_payload=self._payload(note="conflict"),
            )
        self.assertEqual(
            AuditEvent.objects.filter(medical_document_id=medical.id).count(),
            audits_before_conflict,
        )
        self.assertGreater(
            AuditEvent.objects.filter(medical_document_id=medical.id).count(), before
        )

    def test_get_document_lock_state_does_not_write_audit(self) -> None:
        doc, _sess = self._make_locked_draft()
        before = AuditEvent.objects.filter(medical_document_id=doc.id).count()
        effective, name, locked_at = get_document_lock_state(doc)
        self.assertTrue(effective)
        self.assertIsNotNone(name)
        self.assertIsNotNone(locked_at)
        self.assertEqual(
            AuditEvent.objects.filter(medical_document_id=doc.id).count(), before
        )

    def test_metrics_scrape_does_not_write_audit(self) -> None:
        doc, _sess = self._make_locked_draft()
        before = AuditEvent.objects.count()
        payload = build_metrics_payload()
        self.assertIn(b"cogitomedica_doctors_editing", payload)
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_publish_source_locks_document_before_version(self) -> None:
        source = inspect.getsource(publish_document_version)
        doc_idx = source.find("MedicalDocument.objects.select_for_update()")
        ver_idx = source.find("MedicalDocumentVersion.objects.select_for_update()")
        outbox_idx = source.find("OutboxEvent.objects.get_or_create")
        self.assertGreaterEqual(doc_idx, 0)
        self.assertGreater(ver_idx, doc_idx)
        self.assertGreater(outbox_idx, ver_idx)
        # Publish must not take a row lock on OutboxEvent (avoids A↔B deadlock with processor).
        self.assertNotIn(
            "OutboxEvent.objects.select_for_update",
            source,
        )

    def test_edit_session_locks_staff_user_before_document(self) -> None:
        source = inspect.getsource(start_doctor_edit_session)
        user_idx = source.find("StaffUser.objects.select_for_update()")
        doc_idx = source.find("MedicalDocument.objects.select_for_update()")
        self.assertGreaterEqual(user_idx, 0)
        self.assertGreater(doc_idx, user_idx)
        self.assertEqual(source.count("StaffUser.objects.select_for_update()"), 1)

        from apps.medical.services import refresh_document_lock
        from apps.medical.write_gate import (
            mutate_doctor_discard_revision,
            mutate_doctor_publish,
            mutate_doctor_save_draft,
        )

        for fn in (
            mutate_doctor_save_draft,
            mutate_doctor_publish,
            mutate_doctor_discard_revision,
            refresh_document_lock,
        ):
            body = inspect.getsource(fn)
            self.assertNotIn(
                "StaffUser.objects.select_for_update",
                body,
                msg=f"{fn.__name__} must not lock StaffUser (document-only path)",
            )


class PublishOutboxLockOrderConcurrencyTests(TransactionTestCase):
    def setUp(self) -> None:
        self.doctor = StaffUser.objects.create_user(
            username="pub-outbox-doc",
            email="pub-outbox@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        clinic = ClinicSite.objects.create(code="POX", name="Pub Outbox")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        self.queue = DailyQueue.objects.create(
            queue_date=date.today(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=self.doctor,
        )

    def _make_ready_draft(self) -> tuple[MedicalDocument, DoctorEditSessionResult]:
        suffix = uuid.uuid4().hex[:8]
        patient = Patient.objects.create(
            first_name="PO",
            last_name=f"P{suffix}",
            date_of_birth=date(1990, 1, 1),
            phone=f"49172{suffix[:8]}",
            email=f"po.{suffix}@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=int(suffix[:4], 16) % 9000 + 1,
            created_by_user=self.doctor,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.doctor,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="q" * 64,
        )
        doc = MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        sess = start_doctor_edit_session(
            medical_document_id=doc.id, user=self.doctor, purpose="edit"
        )
        payload = {
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        }
        saved = mutate_doctor_save_draft(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=0,
            draft_save_request_id=uuid.uuid4(),
            medical_payload_schema_version=1,
            medical_payload=payload,
        )
        mark_doctor_draft_previewed(
            medical_document_id=doc.id,
            user=self.doctor,
            edit_session_token=sess.edit_session_token,
            expected_draft_revision=saved.draft_revision,
        )
        return doc, sess

    def test_concurrent_publish_and_outbox_process_no_deadlock(self) -> None:
        doc_a, sess_a = self._make_ready_draft()
        doc_b, _sess_b = self._make_ready_draft()
        # Seed a pending outbox row on doc_b's draft so the processor has work.
        draft_b = MedicalDocumentVersion.objects.filter(
            medical_document_id=doc_b.id, version_status=DocVersionStatus.DRAFT
        ).latest("version_no")
        OutboxEvent.objects.create(
            medical_document_version=draft_b,
            event_type=OutboxEventType.GENERATE_PDF,
            aggregate_id=draft_b.id,
            payload_schema_version=1,
            payload={"medical_document_id": str(doc_b.id)},
            status=OutboxStatus.PENDING,
            available_at=timezone.now(),
        )

        errors: list[str] = []
        barrier = threading.Barrier(2)

        def publish() -> None:
            try:
                barrier.wait(timeout=15)
                mutate_doctor_publish(
                    medical_document_id=doc_a.id,
                    user=self.doctor,
                    edit_session_token=sess_a.edit_session_token,
                    expected_draft_revision=1,
                    publish_request_id=uuid.uuid4(),
                    publish_locale="de-DE",
                )
            except Exception as exc:  # noqa: BLE001 — collect for assertion
                errors.append(f"publish:{exc}")
            finally:
                connection.close()

        def process() -> None:
            try:
                barrier.wait(timeout=15)
                with patch(
                    "apps.outbox.services._execute_event",
                    return_value=None,
                ):
                    process_outbox_events(batch_size=5)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"outbox:{exc}")
            finally:
                connection.close()

        t1 = threading.Thread(target=publish)
        t2 = threading.Thread(target=process)
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(errors, [])
        doc_a.refresh_from_db()
        self.assertEqual(doc_a.status, MedicalDocStatus.PUBLISHED)
