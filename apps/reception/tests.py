from __future__ import annotations

from datetime import date

from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.intake.models import PatientIntakeForm
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    ImportStatus,
    Patient,
    PatientImportBatch,
    PatientImportError,
    PatientFormSession,
    QueueEntry,
    QueueStatus,
    TabletDevice,
)
from apps.core.api_utils import assign_group_to_test_user
from apps.reception.services import (
    create_or_update_patient_manual,
    create_queue_entry,
    issue_tablet_session_latest_wins,
)
from apps.reception.xlsx_import import _cleanup_clinic_name, _parse_date, _split_full_name, _title_case_name
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

    def test_create_or_update_patient_manual_allows_missing_doctolib_id(self) -> None:
        patient = create_or_update_patient_manual(
            first_name="Jan",
            last_name="Nowak",
            date_of_birth=date(1990, 1, 1),
            phone="+48123123123",
            email="jan.nowak@example.com",
            doctolib_patient_id=None,
            created_or_updated_by_user_id=self.reception_user.id,
        )

        self.assertIsNone(patient.doctolib_patient_id)
        self.assertEqual(patient.first_name, "Jan")
        self.assertEqual(patient.phone, "48123123123")

    def test_patient_identity_unique_constraint_blocks_duplicate_patient(self) -> None:
        Patient.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            date_of_birth=date(1985, 5, 5),
            phone="+48999999999",
            email="anna.k@example.com",
        )

        with self.assertRaises(IntegrityError):
            Patient.objects.create(
                first_name="Anna",
                last_name="Kowalska",
                date_of_birth=date(1985, 5, 5),
                phone="+48999999999",
                email="other@example.com",
            )

    def test_doctolib_patient_id_remains_unique(self) -> None:
        Patient.objects.create(
            first_name="Anna",
            last_name="Kowalska",
            date_of_birth=date(1985, 5, 5),
            phone="+48999999999",
            email="anna.k@example.com",
            doctolib_patient_id="DOC-123",
        )

        with self.assertRaises(IntegrityError):
            Patient.objects.create(
                first_name="Other",
                last_name="Patient",
                date_of_birth=date(1990, 1, 1),
                phone="+48111111111",
                email="other@example.com",
                doctolib_patient_id="DOC-123",
            )

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


class DailyQueueAdminImportTests(TestCase):
    """Tests for admin import-from-file UI (XLSX upload)."""

    def setUp(self) -> None:
        self.client = Client()
        self.admin_user = StaffUser.objects.create_superuser(
            username="admin-import",
            email="admin-import@example.com",
            password="safe-password",
        )
        self.client.force_login(self.admin_user)

    def test_daily_queue_changelist_contains_import_button(self) -> None:
        response = self.client.get(reverse("admin:reception_dailyqueue_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import z pliku")
        self.assertContains(response, reverse("admin:reception_dailyqueue_import_xlsx"))

    def test_import_xlsx_admin_view_renders_form(self) -> None:
        response = self.client.get(reverse("admin:reception_dailyqueue_import_xlsx"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import pacjentów z pliku XLSX")
        self.assertContains(response, "Plik XLSX")
        self.assertContains(response, "Import odczyta z pliku datę kolejki i nazwę placówki")


class XlsxImportParsingTests(TestCase):
    def test_cleanup_clinic_name_removes_trailing_weekday_and_date(self) -> None:
        cleaned = _cleanup_clinic_name("Kreutzigerstraße Freitag, 6. März")
        self.assertEqual(cleaned, "Kreutzigerstraße")

    def test_parse_date_accepts_dob_with_age_suffix(self) -> None:
        parsed = _parse_date("4.07.1996 (30 Jahre)")
        self.assertEqual(parsed, date(1996, 7, 4))

    def test_split_full_name_removes_title_and_symbol(self) -> None:
        first_name, last_name = _split_full_name("Herr FRITSCHE Sebastian @")
        self.assertEqual(first_name, "Sebastian")
        self.assertEqual(last_name, "FRITSCHE")

    def test_split_full_name_handles_frau_format(self) -> None:
        first_name, last_name = _split_full_name("Frau JURGA Jolina")
        self.assertEqual(first_name, "Jolina")
        self.assertEqual(last_name, "JURGA")

    def test_title_case_name_normalizes_case(self) -> None:
        self.assertEqual(_title_case_name("aLeXanDra"), "Alexandra")
        self.assertEqual(_title_case_name("nIzhENKO"), "Nizhenko")
        self.assertEqual(_title_case_name("o'NEIL-smITH"), "O'Neil-Smith")


class TabletWebLoginLastSeenTests(TestCase):
    def test_tablet_login_with_android_id_sets_last_seen_at(self) -> None:
        client = Client()
        user = StaffUser.objects.create_user(
            username="tablet-login-seen",
            email="tablet-login-seen@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(user, "Tablet")
        device = TabletDevice.objects.create(android_id="web-login-android-seen", is_active=True)
        self.assertIsNone(device.last_seen_at)
        response = client.post(
            "/tablet/login/",
            data={
                "username": "tablet-login-seen",
                "password": "safe-password",
                "android_id": "web-login-android-seen",
            },
        )
        self.assertEqual(response.status_code, 302)
        device.refresh_from_db()
        self.assertIsNotNone(device.last_seen_at)
