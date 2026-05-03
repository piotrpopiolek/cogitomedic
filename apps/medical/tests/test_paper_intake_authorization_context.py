"""Coverage for ``_paper_intake_authorization_context_for_document`` audit parsing."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
)
from apps.medical.services import _paper_intake_authorization_context_for_document
from apps.operations.models import AuditEvent
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


class PaperIntakeAuthorizationContextTests(TestCase):
    def setUp(self) -> None:
        self.doctor = StaffUser.objects.create_user(
            username="ctx-doc",
            email="ctx.doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.rec = StaffUser.objects.create_user(
            username="ctx-rec",
            email="ctx.rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.rec, "Reception")
        clinic = ClinicSite.objects.create(code="CTX", name="Context Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="R1")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.rec,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="C",
            last_name="CtxPatient",
            date_of_birth=date(1990, 1, 1),
            phone="+48111222333",
            email="ctx.patient@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PAPER_INTAKE_COMPLETED,
            position_no=1,
            created_by_user=self.rec,
        )
        self.doc = MedicalDocument.objects.create(
            queue_entry=self.entry,
            intake_form=None,
            source_type=MedicalDocumentSourceType.PAPER_INTAKE,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )

    def test_returns_none_for_digital_intake_source(self) -> None:
        clinic = ClinicSite.objects.create(code="CTX2", name="Context Clinic 2")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="R2", name="R2")
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.rec,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="D",
            last_name="DigitalOnly",
            date_of_birth=date(1991, 2, 2),
            phone="+48222333444",
            email="digital.only@example.com",
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=self.rec,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.rec,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="d" * 64,
        )
        digital = MedicalDocument.objects.create(
            queue_entry=entry,
            intake_form=intake,
            source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        self.assertIsNone(_paper_intake_authorization_context_for_document(digital))

    def test_returns_none_without_audit_event(self) -> None:
        self.assertIsNone(_paper_intake_authorization_context_for_document(self.doc))

    def test_returns_none_when_metadata_not_dict(self) -> None:
        AuditEvent.objects.create(
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
            actor_user=self.doctor,
            patient=self.entry.patient,
            medical_document=self.doc,
            context_clinic_site=self.entry.daily_queue.clinic_site,
            metadata=[],  # type: ignore[arg-type]
        )
        self.assertIsNone(_paper_intake_authorization_context_for_document(self.doc))

    def test_parses_authorizer_and_handles_bad_uuid_and_missing_user(self) -> None:
        bad_meta = AuditEvent.objects.create(
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
            actor_user=self.doctor,
            patient=self.entry.patient,
            medical_document=self.doc,
            context_clinic_site=self.entry.daily_queue.clinic_site,
            metadata={
                "paper_intake_authorized_by_id": "not-a-uuid",
                "paper_intake_authorization_reason_snapshot": 123,
                "paper_intake_authorized_at": 456,
            },
        )
        ctx = _paper_intake_authorization_context_for_document(self.doc)
        self.assertIsNotNone(ctx)
        self.assertIsNone(ctx["authorized_by_user_id"])
        self.assertIsNone(ctx["authorized_at"])
        self.assertIsNone(ctx["reason"])

        bad_meta.delete()
        missing_id = uuid.uuid4()
        AuditEvent.objects.create(
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
            actor_user=self.doctor,
            patient=self.entry.patient,
            medical_document=self.doc,
            context_clinic_site=self.entry.daily_queue.clinic_site,
            metadata={
                "paper_intake_authorized_by_id": str(missing_id),
                "paper_intake_authorization_reason_snapshot": "snap reason ok",
                "paper_intake_authorized_at": "2026-01-02T12:00:00+00:00",
            },
        )
        ctx2 = _paper_intake_authorization_context_for_document(self.doc)
        self.assertEqual(ctx2["authorized_by_username"], str(missing_id))
        self.assertEqual(ctx2["reason"], "snap reason ok")
        self.assertEqual(ctx2["authorized_at"], "2026-01-02T12:00:00+00:00")
