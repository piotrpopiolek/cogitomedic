"""Tests for patient_results.document_services (PDF download / document list)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.patient_results.document_services import (
    get_patient_pdf_path,
    list_patient_documents,
    resolve_patient_befund_download,
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


class DocumentServicesBaseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = StaffUser.objects.create_user(
            username="doc-svc-actor",
            email="doc-svc@example.com",
            password="x",
            is_staff=True,
        )
        cls.clinic = ClinicSite.objects.create(code="DS", name="DS Clinic")
        cls.room = ConsultingRoom.objects.create(
            clinic_site=cls.clinic, code="D1", name="D1"
        )
        cls.daily_queue = DailyQueue.objects.create(
            queue_date=date(2026, 3, 1),
            clinic_site=cls.clinic,
            consulting_room=cls.room,
            status=QueueStatus.OPEN,
            created_by_user=cls.actor,
        )
        cls.patient = Patient.objects.create(
            first_name="Ewa",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="48500100200",
            email="ewa@example.com",
        )
        cls.queue_entry = QueueEntry.objects.create(
            daily_queue=cls.daily_queue,
            patient=cls.patient,
            entry_status=QueueEntryStatus.PUBLISHED,
            position_no=1,
            created_by_user=cls.actor,
        )
        cls.session = PatientFormSession.objects.create(
            queue_entry=cls.queue_entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=cls.actor,
        )
        cls.intake = PatientIntakeForm.objects.create(
            queue_entry=cls.queue_entry,
            session=cls.session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )
        cls.medical_doc = MedicalDocument.objects.create(
            queue_entry=cls.queue_entry,
            intake_form=cls.intake,
            status=MedicalDocStatus.PUBLISHED,
            current_version_no=1,
            created_by_user=cls.actor,
        )

    def _published_version(self, *, version_no=1, **overrides):
        defaults = dict(
            medical_document=self.medical_doc,
            version_no=version_no,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            medical_payload_schema_version=1,
            medical_payload={"schema_version": 1},
            pdf_local_path="/media/befund/test.pdf",
            publish_request_id=uuid.uuid4(),
            published_at=timezone.now(),
            publish_locale="de-DE",
        )
        defaults.update(overrides)
        return MedicalDocumentVersion.objects.create(**defaults)


class ListPatientDocumentsTests(DocumentServicesBaseTestCase):
    def test_returns_current_published_version(self):
        v = self._published_version()
        result = list_patient_documents(self.patient.id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["version_id"], str(v.id))
        self.assertEqual(result[0]["document_id"], str(self.medical_doc.id))
        self.assertEqual(result[0]["queue_date"], "2026-03-01")

    def test_excludes_non_current_version(self):
        self.medical_doc.current_version_no = 2
        self.medical_doc.save(update_fields=["current_version_no"])
        self._published_version(version_no=1)
        v2 = self._published_version(version_no=2)
        result = list_patient_documents(self.patient.id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["version_id"], str(v2.id))

    def test_excludes_revoked_version(self):
        self._published_version(revoked_at=timezone.now())
        result = list_patient_documents(self.patient.id)
        self.assertEqual(result, [])

    def test_excludes_retention_deleted_version(self):
        self._published_version(
            local_pdf_deleted_at=timezone.now(),
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )
        result = list_patient_documents(self.patient.id)
        self.assertEqual(result, [])

    def test_excludes_anonymized_version(self):
        self._published_version(anonymization_deleted_at=timezone.now())
        result = list_patient_documents(self.patient.id)
        self.assertEqual(result, [])

    def test_empty_for_unknown_patient(self):
        result = list_patient_documents(uuid.uuid4())
        self.assertEqual(result, [])


class ResolvePatientBefundDownloadTests(DocumentServicesBaseTestCase):
    def test_not_found_for_nonexistent_version(self):
        resolution, version = resolve_patient_befund_download(
            uuid.uuid4(), self.patient.id
        )
        self.assertEqual(resolution, "not_found")
        self.assertIsNone(version)

    def test_not_found_for_wrong_patient(self):
        v = self._published_version()
        other_patient_id = uuid.uuid4()
        resolution, version = resolve_patient_befund_download(v.id, other_patient_id)
        self.assertEqual(resolution, "not_found")
        self.assertIsNone(version)

    def test_not_found_for_anonymized_version(self):
        v = self._published_version(anonymization_deleted_at=timezone.now())
        resolution, version = resolve_patient_befund_download(v.id, self.patient.id)
        self.assertEqual(resolution, "not_found")
        self.assertIsNone(version)

    def test_retention_expired(self):
        v = self._published_version(
            local_pdf_deleted_at=timezone.now(),
            hidrive_sent=True,
            hidrive_sent_at=timezone.now(),
            sms_sent=True,
            sms_sent_at=timezone.now(),
        )
        resolution, version = resolve_patient_befund_download(v.id, self.patient.id)
        self.assertEqual(resolution, "retention_expired")
        self.assertIsNotNone(version)

    def test_ok_for_available_version(self):
        v = self._published_version()
        resolution, version = resolve_patient_befund_download(v.id, self.patient.id)
        self.assertEqual(resolution, "ok")
        self.assertEqual(version.id, v.id)


class GetPatientPdfPathTests(DocumentServicesBaseTestCase):
    def test_returns_none_when_version_not_found(self):
        result = get_patient_pdf_path(uuid.uuid4(), self.patient.id)
        self.assertIsNone(result)

    def test_returns_none_when_no_pdf_local_path(self):
        v = self._published_version(
            pdf_local_path=None,
            pdf_generation_status=PdfStatus.PENDING,
        )
        result = get_patient_pdf_path(v.id, self.patient.id, version=v)
        self.assertIsNone(result)

    def test_returns_none_when_file_does_not_exist(
        self,
    ):
        v = self._published_version(pdf_local_path="/nonexistent/file.pdf")
        result = get_patient_pdf_path(v.id, self.patient.id, version=v)
        self.assertIsNone(result)

    def test_returns_path_for_existing_file(self, tmp_path=None):
        from django.conf import settings

        media = Path(settings.MEDIA_ROOT)
        media.mkdir(parents=True, exist_ok=True)
        pdf = media / "befund" / "test_existing.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4")

        v = self._published_version(pdf_local_path=str(pdf))
        result = get_patient_pdf_path(v.id, self.patient.id, version=v)
        self.assertIsNotNone(result)
        self.assertEqual(result, pdf)
        pdf.unlink(missing_ok=True)

    def test_relative_path_resolved_under_media_root(self):
        from django.conf import settings

        media = Path(settings.MEDIA_ROOT)
        pdf = media / "befund" / "relative_test.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4")

        v = self._published_version(pdf_local_path="befund/relative_test.pdf")
        result = get_patient_pdf_path(v.id, self.patient.id, version=v)
        self.assertIsNotNone(result)
        pdf.unlink(missing_ok=True)

    def test_path_traversal_returns_none(self):
        from django.conf import settings

        outside = Path(settings.MEDIA_ROOT).parent / "outside.pdf"
        outside.write_bytes(b"%PDF-1.4")
        try:
            v = self._published_version(pdf_local_path=str(outside))
            result = get_patient_pdf_path(v.id, self.patient.id, version=v)
            self.assertIsNone(result)
        finally:
            outside.unlink(missing_ok=True)
