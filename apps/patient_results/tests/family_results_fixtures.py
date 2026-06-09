"""Fixtures for family portal results delivery tests (pytest / Django TestCase)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentVersion,
    PdfStatus,
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

TEST_PEPPER_FAMILY = "test-pepper-family"
FIXED_OTP_FAMILY = 481516
QUEUE_DATE = date(2026, 4, 10)


@dataclass(frozen=True)
class MemberBundle:
    """One family member with a published Befund ready for portal listing."""

    key: str
    patient: Patient
    published_version: MedicalDocumentVersion
    portal_phone: str
    date_of_birth: date
    last_name: str


@dataclass
class FamilyResultsFixture:
    actor: StaffUser
    shared_family_a: tuple[MemberBundle, MemberBundle, MemberBundle]
    separate_family_b: tuple[MemberBundle, MemberBundle, MemberBundle]
    collision_pair: tuple[MemberBundle, MemberBundle]
    collision_phone: str
    collision_dob: date

    def member_by_key(self, key: str) -> MemberBundle:
        for bundle in (
            *self.shared_family_a,
            *self.separate_family_b,
            *self.collision_pair,
        ):
            if bundle.key == key:
                return bundle
        raise KeyError(key)

    @staticmethod
    def otp_hash(otp_code: str, *, pepper: str = TEST_PEPPER_FAMILY) -> str:
        return hashlib.sha256(f"{pepper}{otp_code}".encode()).hexdigest()


def build_family_results_fixture() -> FamilyResultsFixture:
    actor = StaffUser.objects.create_user(
        username="family-results-actor",
        email="family.results@example.invalid",
        password="x",
        is_staff=True,
    )
    clinic = ClinicSite.objects.create(code="FAM", name="Family Test Clinic")
    room = ConsultingRoom.objects.create(
        clinic_site=clinic, code="F1", name="Family Room"
    )
    daily_queue = DailyQueue.objects.create(
        queue_date=QUEUE_DATE,
        clinic_site=clinic,
        consulting_room=room,
        status=QueueStatus.OPEN,
        created_by_user=actor,
    )

    shared_phone = "1769001001"
    shared_family_a = (
        _member_bundle(
            key="a1",
            actor=actor,
            daily_queue=daily_queue,
            position_no=1,
            first_name="Alina",
            last_name="Famshared",
            date_of_birth=date(1980, 1, 15),
            phone=shared_phone,
            portal_phone="01769001001",
            email="alina.famshared@example.invalid",
            pdf_suffix="a1",
        ),
        _member_bundle(
            key="a2",
            actor=actor,
            daily_queue=daily_queue,
            position_no=2,
            first_name="Ben",
            last_name="Famshared",
            date_of_birth=date(1985, 6, 20),
            phone=shared_phone,
            portal_phone="01769001001",
            email="ben.famshared@example.invalid",
            pdf_suffix="a2",
        ),
        _member_bundle(
            key="a3",
            actor=actor,
            daily_queue=daily_queue,
            position_no=3,
            first_name="Clara",
            last_name="Famshared",
            date_of_birth=date(1990, 11, 3),
            phone=shared_phone,
            portal_phone="01769001001",
            email="clara.famshared@example.invalid",
            pdf_suffix="a3",
        ),
    )

    separate_family_b = (
        _member_bundle(
            key="b1",
            actor=actor,
            daily_queue=daily_queue,
            position_no=4,
            first_name="Dora",
            last_name="Sepphone",
            date_of_birth=date(1975, 2, 2),
            phone="1769002001",
            portal_phone="01769002001",
            email="dora.sepphone@example.invalid",
            pdf_suffix="b1",
        ),
        _member_bundle(
            key="b2",
            actor=actor,
            daily_queue=daily_queue,
            position_no=5,
            first_name="Erik",
            last_name="Sepphone",
            date_of_birth=date(1978, 7, 7),
            phone="1769002002",
            portal_phone="01769002002",
            email="erik.sepphone@example.invalid",
            pdf_suffix="b2",
        ),
        _member_bundle(
            key="b3",
            actor=actor,
            daily_queue=daily_queue,
            position_no=6,
            first_name="Frida",
            last_name="Sepphone",
            date_of_birth=date(1982, 12, 12),
            phone="1769002003",
            portal_phone="01769002003",
            email="frida.sepphone@example.invalid",
            pdf_suffix="b3",
        ),
    )

    collision_phone = "1769003001"
    collision_dob = date(1995, 5, 5)
    collision_pair = (
        _member_bundle(
            key="c1",
            actor=actor,
            daily_queue=daily_queue,
            position_no=7,
            first_name="Gina",
            last_name="Kowalska",
            date_of_birth=collision_dob,
            phone=collision_phone,
            portal_phone="01769003001",
            email="gina.kowalska@example.invalid",
            pdf_suffix="c1",
        ),
        _member_bundle(
            key="c2",
            actor=actor,
            daily_queue=daily_queue,
            position_no=8,
            first_name="Hans",
            last_name="Nowak",
            date_of_birth=collision_dob,
            phone=collision_phone,
            portal_phone="01769003001",
            email="hans.nowak@example.invalid",
            pdf_suffix="c2",
        ),
    )

    return FamilyResultsFixture(
        actor=actor,
        shared_family_a=shared_family_a,
        separate_family_b=separate_family_b,
        collision_pair=collision_pair,
        collision_phone=collision_phone,
        collision_dob=collision_dob,
    )


def _member_bundle(
    *,
    key: str,
    actor: StaffUser,
    daily_queue: DailyQueue,
    position_no: int,
    first_name: str,
    last_name: str,
    date_of_birth: date,
    phone: str,
    portal_phone: str,
    email: str,
    pdf_suffix: str,
) -> MemberBundle:
    patient = Patient.objects.create(
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
        phone=phone,
        email=email,
    )
    queue_entry = QueueEntry.objects.create(
        daily_queue=daily_queue,
        patient=patient,
        entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        position_no=position_no,
        created_by_user=actor,
    )
    session = PatientFormSession.objects.create(
        queue_entry=queue_entry,
        form_locale="de-DE",
        expires_at=timezone.now() + timedelta(hours=2),
        created_by_user=actor,
    )
    intake = PatientIntakeForm.objects.create(
        queue_entry=queue_entry,
        session=session,
        form_status=IntakeStatus.SUBMITTED,
        submitted_at=timezone.now(),
        signature_sha256="c" * 64,
    )
    medical_doc = MedicalDocument.objects.create(
        queue_entry=queue_entry,
        intake_form=intake,
        status=MedicalDocStatus.PUBLISHED,
        current_version_no=1,
        created_by_user=actor,
    )
    published_version = MedicalDocumentVersion.objects.create(
        medical_document=medical_doc,
        version_no=1,
        version_status=DocVersionStatus.PUBLISHED,
        pdf_generation_status=PdfStatus.COMPLETED,
        medical_payload_schema_version=1,
        medical_payload={"schema_version": 1, "member": key},
        pdf_local_path=f"/media/befund/family_{pdf_suffix}.pdf",
        publish_request_id=uuid.uuid4(),
        published_at=timezone.now(),
        publish_locale="de-DE",
    )
    return MemberBundle(
        key=key,
        patient=patient,
        published_version=published_version,
        portal_phone=portal_phone,
        date_of_birth=date_of_birth,
        last_name=last_name,
    )
