"""Integration tests for apps.reception.anonymization (RODO / Art. 17 flow)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from freezegun import freeze_time

from apps.core.exceptions import DomainError
from apps.core.retention_payloads import ANONYMIZED_INTAKE_SNAPSHOT
from apps.intake.models import (
    ConsentDefinition,
    IntakeDocumentVersion,
    IntakePdfStatus,
    IntakeStatus,
    PatientIntakeConsent,
    PatientIntakeForm,
)
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.operations.models import AuditEvent
from apps.reception.anonymization import (
    _extract_consent_summary,
    anonymize_patient,
)
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


class AnonymizationIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.actor = StaffUser.objects.create_user(
            username="anon-actor",
            email="anon.actor@example.com",
            password="safe-password",
            is_staff=True,
        )
        self.clinic = ClinicSite.objects.create(code="ANON", name="Anon Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="R1", name="Room 1"
        )
        self.daily_queue = DailyQueue.objects.create(
            queue_date=date(2026, 1, 15),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.actor,
        )

    def _patient(self) -> Patient:
        n = uuid.uuid4().int % 9_000_000_000 + 1_000_000_000
        return Patient.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            date_of_birth=date(1985, 5, 5),
            phone=str(n),
            email=f"jan.{n}@example.com",
        )

    def _terminal_entry(
        self, patient: Patient, *, status: str = "PUBLISHED"
    ) -> QueueEntry:
        return QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=patient,
            entry_status=status,
            position_no=1,
            created_by_user=self.actor,
        )

    def test_anonymize_raises_when_non_terminal_queue_entries(self) -> None:
        patient = self._patient()
        QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            created_by_user=self.actor,
        )
        with self.assertRaises(DomainError):
            anonymize_patient(patient.id, actor_user_id=self.actor.id)
        patient.refresh_from_db()
        self.assertIsNone(patient.anonymization_started_at)
        self.assertIsNone(patient.anonymized_at)

    @freeze_time("2026-03-10T12:00:00Z")
    def test_anonymize_happy_path_clears_pii_and_writes_audit(self) -> None:
        patient = self._patient()
        self._terminal_entry(patient)

        out = anonymize_patient(patient.id, actor_user_id=self.actor.id)
        out.refresh_from_db()

        self.assertIsNotNone(out.anonymized_at)
        self.assertEqual(out.first_name, "ANONYMIZED")
        self.assertEqual(out.last_name, "ANONYMIZED")
        self.assertIsNone(out.date_of_birth)
        self.assertEqual(out.email, f"anon-{patient.id}@deleted.invalid")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="PATIENT_ANONYMIZED",
                patient_id=patient.id,
                actor_user_id=self.actor.id,
            ).exists()
        )

    @freeze_time("2026-03-10T12:00:00Z")
    def test_extract_consent_summary_empty_without_submitted_form(self) -> None:
        patient = self._patient()
        session = PatientFormSession.objects.create(
            queue_entry=self._terminal_entry(patient),
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.actor,
        )
        PatientIntakeForm.objects.create(
            queue_entry=session.queue_entry,
            session=session,
            form_status=IntakeStatus.IN_PROGRESS,
            signature_sha256="a" * 64,
        )
        summary = _extract_consent_summary(patient.id)
        self.assertEqual(summary["consents"], [])
        self.assertIsNone(summary["intake_form_id"])

    @freeze_time("2026-03-10T12:00:00Z")
    def test_extract_consent_summary_with_submitted_form_and_consent(self) -> None:
        patient = self._patient()
        qe = self._terminal_entry(patient)
        session = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.actor,
        )
        cdef = ConsentDefinition.objects.create(
            code="GDPR_OK",
            version=1,
            title_de="t",
            content_de="c",
        )
        submitted_at = timezone.now() - timedelta(minutes=5)
        intake = PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=submitted_at,
            signature_sha256="b" * 64,
            anamnesis_payload={"k": "v"},
            body_map_data=[{"x": 1}],
        )
        PatientIntakeConsent.objects.create(
            intake_form=intake,
            consent_definition=cdef,
            accepted=True,
            accepted_at=submitted_at,
        )
        IntakeDocumentVersion.objects.create(
            intake_form=intake,
            version_no=1,
            form_locale="de",
            snapshot_payload={"schema_version": 1, "raw": True},
            pdf_generation_status=IntakePdfStatus.PENDING,
        )

        summary = _extract_consent_summary(patient.id)
        self.assertEqual(summary["intake_form_id"], str(intake.id))
        self.assertEqual(len(summary["consents"]), 1)
        self.assertEqual(summary["consents"][0]["code"], "GDPR_OK")
        self.assertEqual(summary["consents"][0]["version"], 1)
        self.assertTrue(summary["consents"][0]["accepted"])

        anonymize_patient(patient.id, actor_user_id=self.actor.id)
        intake.refresh_from_db()
        self.assertEqual(intake.anamnesis_payload, {})
        self.assertEqual(intake.body_map_data, [])
        doc_v = IntakeDocumentVersion.objects.get(intake_form=intake)
        self.assertEqual(doc_v.snapshot_payload, dict(ANONYMIZED_INTAKE_SNAPSHOT))

    def test_phase2_file_delete_failure_leaves_phase3_skipped_but_phase1_persisted(
        self,
    ) -> None:
        patient = self._patient()
        qe = self._terminal_entry(patient)
        session = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.actor,
        )
        sig_dir = Path(settings.MEDIA_ROOT) / "signatures" / "anon"
        sig_dir.mkdir(parents=True, exist_ok=True)
        sig_path = sig_dir / f"{patient.id}.png"
        sig_path.write_bytes(b"x")
        PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_file_path=str(sig_path),
            signature_sha256=hashlib.sha256(b"x").hexdigest(),
        )

        with patch(
            "apps.reception.anonymization._try_delete_file",
            side_effect=RuntimeError("disk full"),
        ):
            with self.assertRaises(RuntimeError):
                anonymize_patient(patient.id, actor_user_id=self.actor.id)

        patient.refresh_from_db()
        self.assertIsNotNone(patient.anonymization_started_at)
        self.assertIsNone(patient.anonymized_at)
        self.assertFalse(
            AuditEvent.objects.filter(event_type="PATIENT_ANONYMIZED").exists()
        )

    @freeze_time("2026-03-10T12:00:00Z")
    def test_anonymize_idempotent_after_completion(self) -> None:
        patient = self._patient()
        self._terminal_entry(patient)
        first = anonymize_patient(patient.id, actor_user_id=self.actor.id)
        n_audit = AuditEvent.objects.filter(
            event_type="PATIENT_ANONYMIZED", patient_id=patient.id
        ).count()
        second = anonymize_patient(patient.id, actor_user_id=self.actor.id)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            AuditEvent.objects.filter(
                event_type="PATIENT_ANONYMIZED", patient_id=patient.id
            ).count(),
            n_audit,
        )

    @freeze_time("2026-03-10T12:00:00Z")
    def test_resume_after_phase1_completes_phase3(self) -> None:
        patient = self._patient()
        qe = self._terminal_entry(patient)
        session = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.actor,
        )
        sig_dir = Path(settings.MEDIA_ROOT) / "signatures" / "resume"
        sig_dir.mkdir(parents=True, exist_ok=True)
        sig_path = sig_dir / f"{patient.id}.png"
        sig_path.write_bytes(b"sig")
        PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_file_path=str(sig_path),
            signature_sha256=hashlib.sha256(b"sig").hexdigest(),
        )

        with patch(
            "apps.reception.anonymization._try_delete_file",
            side_effect=RuntimeError("fail once"),
        ):
            with self.assertRaises(RuntimeError):
                anonymize_patient(patient.id, actor_user_id=self.actor.id)

        patient.refresh_from_db()
        self.assertIsNotNone(patient.anonymization_started_at)
        self.assertIsNone(patient.anonymized_at)

        anonymize_patient(patient.id, actor_user_id=self.actor.id)
        patient.refresh_from_db()
        self.assertIsNotNone(patient.anonymized_at)
        self.assertEqual(patient.first_name, "ANONYMIZED")


class AnonymizationMedicalDocumentTests(TestCase):
    """Medical PDF paths participate in phase 2 (same patient / queue as intake)."""

    def setUp(self) -> None:
        self.actor = StaffUser.objects.create_user(
            username="anon-doc-actor",
            email="anon.doc@example.com",
            password="safe-password",
            is_staff=True,
        )
        self.clinic = ClinicSite.objects.create(code="MD1", name="MD Clinic")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="D1", name="D1"
        )
        self.daily_queue = DailyQueue.objects.create(
            queue_date=date(2026, 2, 1),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.actor,
        )
        self.patient = Patient.objects.create(
            first_name="Doc",
            last_name="Patient",
            date_of_birth=date(1991, 1, 1),
            phone="48500999001",
            email="doc.patient@example.com",
        )
        self.queue_entry = QueueEntry.objects.create(
            daily_queue=self.daily_queue,
            patient=self.patient,
            entry_status=QueueEntryStatus.PUBLISHED,
            position_no=1,
            created_by_user=self.actor,
        )
        self.session = PatientFormSession.objects.create(
            queue_entry=self.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.actor,
        )
        self.intake = PatientIntakeForm.objects.create(
            queue_entry=self.queue_entry,
            session=self.session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="d" * 64,
        )
        self.medical = MedicalDocument.objects.create(
            queue_entry=self.queue_entry,
            intake_form=self.intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=1,
            created_by_user=self.actor,
        )
        pdf_dir = Path(settings.MEDIA_ROOT) / "befund"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_path = pdf_dir / f"{uuid.uuid4()}.pdf"
        self.pdf_path.write_bytes(b"%PDF-1.4")

    @freeze_time("2026-04-01T10:00:00Z")
    def test_phase2_clears_medical_pdf_path_and_sets_anonymization_deleted_at(
        self,
    ) -> None:
        version = MedicalDocumentVersion.objects.create(
            medical_document=self.medical,
            version_no=1,
            version_status=DocVersionStatus.DRAFT,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path=str(self.pdf_path),
        )

        anonymize_patient(self.patient.id, actor_user_id=self.actor.id)
        version.refresh_from_db()
        self.assertIsNone(version.pdf_local_path)
        self.assertIsNotNone(version.anonymization_deleted_at)
