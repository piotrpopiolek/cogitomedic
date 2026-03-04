from __future__ import annotations

from datetime import date

from django.test import Client, TestCase
from django.utils import timezone

from apps.intake.models import PatientIntakeForm
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientFormSession,
    QueueStatus,
)
from apps.core.api_utils import assign_group_to_test_user
from apps.reception.services import (
    create_or_update_patient_manual,
    create_queue_entry,
    issue_tablet_session_latest_wins,
)
from apps.users.models import StaffUser


class ReceptionServicesTests(TestCase):
    def setUp(self) -> None:
        self.reception_user = StaffUser.objects.create_user(
            username="reception",
            email="reception@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.clinic = ClinicSite.objects.create(code="BER", name="Berlin")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="R1",
            name="Room 1",
        )
        self.daily_queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception_user,
        )

    def test_create_or_update_patient_manual_sets_identity_alert_when_missing_doctolib_id(self) -> None:
        patient = create_or_update_patient_manual(
            first_name="Jan",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="+48123123123",
            email="jan.nowak@example.com",
            doctolib_patient_id=None,
            created_or_updated_by_user_id=self.reception_user.id,
        )

        self.assertEqual(patient.identity_status, "TEMPORARY")
        self.assertIsNotNone(patient.identity_alert_created_at)
        self.assertIsNotNone(patient.identity_resolution_due_at)
        self.assertGreaterEqual(patient.identity_resolution_due_at, patient.identity_alert_created_at)

    def test_create_or_update_patient_manual_clears_alert_when_doctolib_id_present(self) -> None:
        patient = Patient.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            date_of_birth=date(1985, 5, 5),
            phone="+48999999999",
            email="anna.k@example.com",
            doctolib_patient_id=None,
            identity_alert_created_at=timezone.now(),
            identity_resolution_due_at=timezone.now() + timezone.timedelta(hours=24),
        )

        updated = create_or_update_patient_manual(
            patient_id=patient.id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            date_of_birth=patient.date_of_birth,
            phone=patient.phone,
            email=patient.email,
            doctolib_patient_id="DOC-123",
            created_or_updated_by_user_id=self.reception_user.id,
        )

        self.assertEqual(updated.identity_status, "CONFIRMED")
        self.assertIsNone(updated.identity_alert_created_at)
        self.assertIsNone(updated.identity_resolution_due_at)

    def test_create_queue_entry_auto_assigns_next_position(self) -> None:
        patient_one = Patient.objects.create(
            first_name="P1",
            last_name="Test",
            date_of_birth=date(1991, 1, 1),
            phone="+48111111111",
            email="p1@example.com",
            doctolib_patient_id="DOC-P1",
        )
        patient_two = Patient.objects.create(
            first_name="P2",
            last_name="Test",
            date_of_birth=date(1992, 2, 2),
            phone="+48222222222",
            email="p2@example.com",
            doctolib_patient_id="DOC-P2",
        )

        first = create_queue_entry(
            daily_queue_id=self.daily_queue.id,
            patient_id=patient_one.id,
            created_by_user_id=self.reception_user.id,
        )
        second = create_queue_entry(
            daily_queue_id=self.daily_queue.id,
            patient_id=patient_two.id,
            created_by_user_id=self.reception_user.id,
        )

        self.assertEqual(first.position_no, 1)
        self.assertEqual(second.position_no, 2)

    def test_issue_tablet_session_latest_wins_switches_active_session(self) -> None:
        patient = Patient.objects.create(
            first_name="Tablet",
            last_name="Patient",
            date_of_birth=date(1993, 3, 3),
            phone="+48333333333",
            email="tablet@example.com",
            doctolib_patient_id="DOC-P3",
        )
        queue_entry = create_queue_entry(
            daily_queue_id=self.daily_queue.id,
            patient_id=patient.id,
            created_by_user_id=self.reception_user.id,
        )

        first_result = issue_tablet_session_latest_wins(
            queue_entry_id=queue_entry.id,
            created_by_user_id=self.reception_user.id,
            form_locale="de-DE",
        )
        second_result = issue_tablet_session_latest_wins(
            queue_entry_id=queue_entry.id,
            created_by_user_id=self.reception_user.id,
            form_locale="en-GB",
        )

        queue_entry.refresh_from_db()
        self.assertEqual(queue_entry.active_session_id, second_result.session_id)
        self.assertNotEqual(first_result.session_id, second_result.session_id)

        self.assertEqual(
            PatientFormSession.objects.filter(queue_entry=queue_entry).count(),
            2,
        )
        self.assertEqual(first_result.intake_form_id, second_result.intake_form_id)
        intake_form = PatientIntakeForm.objects.get(queue_entry=queue_entry)
        self.assertEqual(intake_form.session_id, second_result.session_id)

    def test_patients_api_view_doctor_filtered(self) -> None:
        doctor_user = StaffUser.objects.create_user(
            username="doc_test",
            email="doc_test@example.com",
            password="pwd",
            is_staff=True,
        )
        assign_group_to_test_user(doctor_user, "Doctor")
        # Assign clinic to doctor
        doctor_user.clinic_sites.add(self.clinic)
        
        # Create a patient assigned to self.clinic
        patient1 = Patient.objects.create(
            first_name="Test1",
            last_name="Test1",
            date_of_birth=date(1991, 1, 1),
            phone="+48111111111",
            email="test1@example.com"
        )
        patient1.clinic_sites.add(self.clinic)

        # Create a patient NOT assigned to self.clinic
        other_clinic = ClinicSite.objects.create(code="OTH", name="Other")
        patient2 = Patient.objects.create(
            first_name="Test2",
            last_name="Test2",
            date_of_birth=date(1991, 1, 1),
            phone="+48111111112",
            email="test2@example.com"
        )
        patient2.clinic_sites.add(other_clinic)

        client = Client()
        client.force_login(doctor_user)
        response = client.get("/api/v1/patients")
        self.assertEqual(response.status_code, 200)
        
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(patient1.id))
