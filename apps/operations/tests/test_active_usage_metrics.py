"""Active doctors / patient-portal usage gauges (ORM scrape)."""

from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import MedicalDocStatus, MedicalDocument
from apps.operations.prom_metrics import _OrmMetricsCollector
from apps.operations.services import create_audit_event
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


def _gauge_samples(name: str) -> dict[tuple[str, ...], float]:
    out: dict[tuple[str, ...], float] = {}
    for family in _OrmMetricsCollector().collect():
        if family.name != name:
            continue
        for sample in family.samples:
            key: tuple[str, ...]
            if name == "cogitomedica_active_users":
                key = (sample.labels["channel"], sample.labels["window"])
            else:
                key = ()
            out[key] = float(sample.value)
    return out


class ActiveUsageMetricsTests(TestCase):
    def setUp(self) -> None:
        self.now = timezone.now()
        self.doctor = StaffUser.objects.create_user(
            username="doc-usage-met",
            email="doc-usage-met@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.reception = StaffUser.objects.create_user(
            username="rec-usage-met",
            email="rec-usage-met@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.clinic = ClinicSite.objects.create(code="USG", name="Usage metrics")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="R1", name="R1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
        )
        self.patient = Patient.objects.create(
            first_name="Usage",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            phone="491701112200",
            email="usage.patient@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=self.patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            created_by_user=self.reception,
        )
        session = PatientFormSession.objects.create(
            queue_entry=self.entry,
            form_locale="de-DE",
            expires_at=self.now + timedelta(hours=1),
            created_by_user=self.reception,
        )
        self.intake = PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=session,
            form_status=IntakeStatus.SUBMITTED,
            signature_file_path="/tmp/sig-usage.png",
            signature_sha256="d" * 64,
            submitted_at=self.now,
        )
        self.doc = MedicalDocument.objects.create(
            queue_entry=self.entry,
            intake_form=self.intake,
            status=MedicalDocStatus.DRAFT,
            created_by_user=self.doctor,
        )

    def test_active_doctors_from_last_login_and_audit(self) -> None:
        StaffUser.objects.filter(pk=self.doctor.pk).update(last_login=self.now)
        samples = _gauge_samples("cogitomedica_active_users")
        self.assertGreaterEqual(samples.get(("doctor", "15m"), 0.0), 1.0)
        self.assertGreaterEqual(samples.get(("doctor", "60m"), 0.0), 1.0)

        StaffUser.objects.filter(pk=self.doctor.pk).update(
            last_login=self.now - timedelta(hours=2)
        )
        create_audit_event(
            event_type="DOCUMENT_DRAFT_SAVED",
            actor_user_id=self.doctor.id,
            medical_document_id=self.doc.id,
            patient_id=self.patient.id,
            context_clinic_site_id=self.clinic.id,
        )
        samples = _gauge_samples("cogitomedica_active_users")
        self.assertGreaterEqual(samples.get(("doctor", "15m"), 0.0), 1.0)

    def test_doctors_editing_from_active_lock(self) -> None:
        self.doc.locked_by_user = self.doctor
        self.doc.locked_at = self.now
        self.doc.save(update_fields=["locked_by_user", "locked_at"])
        samples = _gauge_samples("cogitomedica_doctors_editing")
        self.assertEqual(samples.get((), 0.0), 1.0)

        self.doc.locked_at = self.now - timedelta(hours=7)
        self.doc.save(update_fields=["locked_at"])
        samples = _gauge_samples("cogitomedica_doctors_editing")
        self.assertEqual(samples.get((), 0.0), 0.0)

    def test_patient_portal_activity_counts_distinct_patients(self) -> None:
        create_audit_event(
            event_type="PATIENT_RESULTS_OTP_VERIFY",
            patient_id=self.patient.id,
            metadata={"outcome": "ok"},
        )
        create_audit_event(
            event_type="PATIENT_RESULTS_DOCUMENTS_LISTED",
            patient_id=self.patient.id,
        )
        # Same patient twice — still 1 distinct.
        samples = _gauge_samples("cogitomedica_active_users")
        self.assertEqual(samples.get(("patient_portal", "15m"), 0.0), 1.0)
        self.assertEqual(samples.get(("patient_portal", "60m"), 0.0), 1.0)

        other = Patient.objects.create(
            first_name="Other",
            last_name="Portal",
            date_of_birth=date(1991, 2, 2),
            phone="491701112201",
            email="other.portal@example.com",
        )
        create_audit_event(
            event_type="PATIENT_RESULTS_PDF_DOWNLOAD",
            patient_id=other.id,
        )
        samples = _gauge_samples("cogitomedica_active_users")
        self.assertEqual(samples.get(("patient_portal", "15m"), 0.0), 2.0)

    def test_otp_request_alone_does_not_count_as_portal_usage(self) -> None:
        create_audit_event(
            event_type="PATIENT_RESULTS_OTP_REQUEST",
            patient_id=self.patient.id,
            metadata={"outcome": "sent"},
        )
        samples = _gauge_samples("cogitomedica_active_users")
        self.assertEqual(samples.get(("patient_portal", "15m"), 0.0), 0.0)

    def test_payload_contains_active_user_metrics(self) -> None:
        from apps.operations.prom_metrics import build_metrics_payload

        payload = build_metrics_payload().decode("utf-8")
        self.assertIn("cogitomedica_active_users", payload)
        self.assertIn("cogitomedica_doctors_editing", payload)
        self.assertIn('channel="doctor"', payload)
        self.assertIn('channel="patient_portal"', payload)
        self.assertIn('window="15m"', payload)
