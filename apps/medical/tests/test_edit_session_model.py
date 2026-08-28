"""Tests for edit-session model fields, migration cutover, and lock predicate."""

from __future__ import annotations

import importlib

from django.apps import apps
from django.utils import timezone

from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocumentSourceType,
)
from apps.medical.edit_session import doctor_befund_edit_lock_applies
from apps.medical.tests.test_services_coverage import ServicesCoverageBase

_clear_legacy_edit_locks = importlib.import_module(
    "apps.medical.migrations.0023_medicaldocument_edit_session_fields"
).clear_legacy_edit_locks


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
            intake_form=None,
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


class MedicalDocumentEditSessionCutoverTests(ServicesCoverageBase):
    def test_clear_legacy_edit_locks_resets_holder_and_session_markers(self) -> None:
        doc = self._make_medical_doc(status=MedicalDocStatus.DRAFT)
        doc.locked_by_user = self.doctor
        doc.locked_at = timezone.now()
        doc.edit_session_token = None
        doc.last_previewed_draft_revision = 3
        doc.save(
            update_fields=[
                "locked_by_user",
                "locked_at",
                "edit_session_token",
                "last_previewed_draft_revision",
            ]
        )

        _clear_legacy_edit_locks(apps, None)

        doc.refresh_from_db()
        self.assertIsNone(doc.locked_by_user_id)
        self.assertIsNone(doc.locked_at)
        self.assertIsNone(doc.edit_session_token)
        self.assertIsNone(doc.last_edit_session_request_id)
        self.assertIsNone(doc.last_previewed_draft_revision)
        self.assertEqual(doc.draft_revision, 0)
        self.assertEqual(doc.edit_session_revision, 0)
