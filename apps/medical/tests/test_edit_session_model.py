"""Tests for edit-session model fields, migration cutover, and lock predicate."""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.utils import timezone

from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
)
from apps.medical.services import doctor_befund_edit_lock_applies
from apps.medical.tests.test_services_coverage import ServicesCoverageBase


class DoctorBefundEditLockAppliesTests(ServicesCoverageBase):
    def test_applies_for_digital_intake_draft(self) -> None:
        doc = self._make_medical_doc(
            source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            status=MedicalDocStatus.DRAFT,
        )
        self.assertTrue(doctor_befund_edit_lock_applies(doc))

    def test_applies_for_published_with_pending_revision(self) -> None:
        doc = self._make_medical_doc(
            source_type=MedicalDocumentSourceType.PAPER_INTAKE,
            status=MedicalDocStatus.PUBLISHED,
            has_pending_revision=True,
        )
        self.assertTrue(doctor_befund_edit_lock_applies(doc))

    def test_not_for_clean_published(self) -> None:
        doc = self._make_medical_doc(
            status=MedicalDocStatus.PUBLISHED,
            has_pending_revision=False,
        )
        self.assertFalse(doctor_befund_edit_lock_applies(doc))

    def test_not_for_external_upload_even_when_draft(self) -> None:
        doc = self._make_medical_doc(
            source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD,
            status=MedicalDocStatus.DRAFT,
        )
        self.assertFalse(doctor_befund_edit_lock_applies(doc))


class MedicalDocumentEditSessionFieldDefaultsTests(ServicesCoverageBase):
    def test_new_document_has_zero_revisions_and_null_session_fields(self) -> None:
        doc = self._make_medical_doc(status=MedicalDocStatus.DRAFT)
        doc.refresh_from_db()
        self.assertEqual(doc.draft_revision, 0)
        self.assertEqual(doc.edit_session_revision, 0)
        self.assertIsNone(doc.edit_session_token)
        self.assertIsNone(doc.last_previewed_draft_revision)
        self.assertIsNone(doc.last_draft_request_id)
        self.assertIsNone(doc.last_draft_request_base_revision)
        self.assertIsNone(doc.last_draft_request_result_revision)
        self.assertIsNone(doc.last_edit_session_request_id)


class MedicalDocumentEditSessionMigrationTests(TestCase):
    migrate_from = ("medical", "0022_alter_externalpdfattachment_status")
    migrate_to = ("medical", "0023_medicaldocument_edit_session_fields")

    def _apply_migration(self, target: tuple[str, str]) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)

    def test_cutover_clears_legacy_locks_and_sets_defaults(self) -> None:
        self._apply_migration(self.migrate_from)

        MedicalDocument = apps.get_model("medical", "MedicalDocument")
        StaffUser = apps.get_model("users", "StaffUser")
        ClinicSite = apps.get_model("reception", "ClinicSite")
        ConsultingRoom = apps.get_model("reception", "ConsultingRoom")
        DailyQueue = apps.get_model("reception", "DailyQueue")
        Patient = apps.get_model("reception", "Patient")
        QueueEntry = apps.get_model("reception", "QueueEntry")
        PatientIntakeForm = apps.get_model("intake", "PatientIntakeForm")
        PatientFormSession = apps.get_model("reception", "PatientFormSession")

        doctor = StaffUser.objects.create_user(
            username="mig-doc",
            email="mig-doc@example.com",
            password="x",
            is_staff=True,
        )
        clinic = ClinicSite.objects.create(code="MIG", name="Migration Clinic")
        room = ConsultingRoom.objects.create(
            clinic_site=clinic,
            code="M1",
            name="M1",
        )
        daily_queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=clinic,
            consulting_room=room,
            status="OPEN",
            assigned_doctor=doctor,
            created_by_user=doctor,
        )
        patient = Patient.objects.create(
            first_name="Max",
            last_name="Mustermann",
            date_of_birth=timezone.localdate().replace(year=1980),
            phone="491234567890",
            email="max@example.com",
        )
        queue_entry = QueueEntry.objects.create(
            daily_queue=daily_queue,
            patient=patient,
            entry_status="PATIENT_COMPLETED",
            position_no=1,
            created_by_user=doctor,
        )
        session = PatientFormSession.objects.create(
            queue_entry=queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=doctor,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=queue_entry,
            session=session,
            form_status="SUBMITTED",
            submitted_at=timezone.now(),
            signature_sha256="b" * 64,
        )
        doc = MedicalDocument.objects.create(
            queue_entry=queue_entry,
            intake_form=intake,
            source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=doctor,
            locked_by_user=doctor,
            locked_at=timezone.now(),
        )

        self._apply_migration(self.migrate_to)

        doc.refresh_from_db()
        self.assertIsNone(doc.locked_by_user_id)
        self.assertIsNone(doc.locked_at)
        self.assertIsNone(doc.edit_session_token)
        self.assertIsNone(doc.last_edit_session_request_id)
        self.assertIsNone(doc.last_previewed_draft_revision)
        self.assertEqual(doc.draft_revision, 0)
        self.assertEqual(doc.edit_session_revision, 0)
