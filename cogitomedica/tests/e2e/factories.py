"""Shared fixtures for Befund edit-session Playwright E2E."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
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


def create_doctor(*, username: str, password: str = "x") -> StaffUser:
    user = StaffUser.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        is_staff=True,
        first_name=username[:20],
        last_name="Arzt",
    )
    assign_group_to_test_user(user, "Doctor")
    return user


def create_clinic_queue(*, doctor: StaffUser, code: str = "E2E") -> DailyQueue:
    clinic = ClinicSite.objects.create(code=code, name=f"Clinic {code}")
    room = ConsultingRoom.objects.create(clinic_site=clinic, code="R1", name="Room 1")
    return DailyQueue.objects.create(
        queue_date=date.today(),
        clinic_site=clinic,
        consulting_room=room,
        status=QueueStatus.OPEN,
        assigned_doctor=doctor,
        created_by_user=doctor,
    )


def create_draft_document(
    *,
    doctor: StaffUser,
    daily_queue: DailyQueue,
    position_no: int = 1,
    patient_last: str | None = None,
) -> MedicalDocument:
    suffix = uuid.uuid4().hex[:8]
    patient = Patient.objects.create(
        first_name="E2E",
        last_name=patient_last or f"Patient{suffix}",
        date_of_birth=date(1980, 1, 15),
        phone=f"49170{suffix[:8]}",
        email=f"e2e.{suffix}@example.com",
    )
    entry = QueueEntry.objects.create(
        daily_queue=daily_queue,
        patient=patient,
        entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        position_no=position_no,
        created_by_user=doctor,
    )
    session = PatientFormSession.objects.create(
        queue_entry=entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(hours=2),
        created_by_user=doctor,
    )
    intake = PatientIntakeForm.objects.create(
        queue_entry=entry,
        session=session,
        form_status=IntakeStatus.SUBMITTED,
        submitted_at=timezone.now(),
        signature_sha256="e" * 64,
    )
    return MedicalDocument.objects.create(
        queue_entry=entry,
        intake_form=intake,
        status=MedicalDocStatus.DRAFT,
        current_version_no=0,
        created_by_user=doctor,
    )


def create_published_document(
    *,
    doctor: StaffUser,
    daily_queue: DailyQueue,
    position_no: int = 50,
) -> MedicalDocument:
    doc = create_draft_document(
        doctor=doctor,
        daily_queue=daily_queue,
        position_no=position_no,
        patient_last=f"Pub{uuid.uuid4().hex[:6]}",
    )
    MedicalDocumentVersion.objects.create(
        medical_document=doc,
        version_no=1,
        version_status=DocVersionStatus.PUBLISHED,
        medical_payload_schema_version=1,
        medical_payload={
            "schema_version": 1,
            "authoring_locale": "de-DE",
            "lesions": [],
            "examination_scope": ["INTIMATE_AREA_NOT_EXAMINED"],
            "fitzpatrick_type": "TYPE_III",
            "overall_image_assessment": "NO_CONTROL_NEEDED",
            "recommendations": ["NO_SHORT_TERM_FOLLOWUP_REQUIRED"],
            "final_assessment": "NO_HIGH_GRADE_SUSPICION",
        },
        published_by_user=doctor,
        published_at=timezone.now(),
        publish_locale="de-DE",
        publish_request_id=uuid.uuid4(),
    )
    doc.status = MedicalDocStatus.PUBLISHED
    doc.current_version_no = 1
    doc.published_version_no = 1
    doc.has_pending_revision = False
    doc.save(
        update_fields=[
            "status",
            "current_version_no",
            "published_version_no",
            "has_pending_revision",
            "updated_at",
        ]
    )
    return doc
