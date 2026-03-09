from __future__ import annotations

import os
import tempfile
from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
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
)
from apps.core.api_utils import assign_group_to_test_user
from apps.reception.pdf_import import (
    DoctolibPdfParser,
    ParsedPatientRow,
    ParsedPdfImport,
    PatientPdfImportErrorCode,
    PatientPdfImportFailure,
    process_patient_pdf_import_batch,
)
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
        self.assertEqual(patient.phone, "+48123123123")

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


class FakePdfPage:
    def __init__(self, *, text: str, words: list[dict]) -> None:
        self._text = text
        self._words = words

    def extract_text(self) -> str:
        return self._text

    def extract_words(self, **kwargs) -> list[dict]:
        return self._words


class FakePdfDocument:
    def __init__(self, pages: list[FakePdfPage]) -> None:
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class PatientPdfParserTests(TestCase):
    def test_parse_extracts_header_and_rows(self) -> None:
        parser = DoctolibPdfParser()
        fake_pdf = FakePdfDocument(
            [
                FakePdfPage(
                    text=(
                        "Clinic: Berlin Central\n"
                        "Date: 08.03.2026\n"
                        "Godzina Imie nazwisko Telefon Data urodzenia Email Adres Kod pocztowy\n"
                        "08:30 Anna Nowak +49111111111 01.01.1990 anna@example.com Main 1 10115\n"
                        "09:00 Jan Kowalski +49222222222 02.02.1985 jan@example.com Side 2 10999"
                    ),
                    words=[
                        {"text": "Clinic:", "x0": 10, "x1": 30, "top": 10, "bottom": 12},
                        {"text": "Berlin", "x0": 40, "x1": 70, "top": 10, "bottom": 12},
                        {"text": "Central", "x0": 75, "x1": 110, "top": 10, "bottom": 12},
                        {"text": "Date:", "x0": 10, "x1": 25, "top": 20, "bottom": 22},
                        {"text": "08.03.2026", "x0": 40, "x1": 85, "top": 20, "bottom": 22},
                        {"text": "Godzina", "x0": 10, "x1": 45, "top": 30, "bottom": 32},
                        {"text": "Imie", "x0": 80, "x1": 100, "top": 30, "bottom": 32},
                        {"text": "nazwisko", "x0": 105, "x1": 145, "top": 30, "bottom": 32},
                        {"text": "Telefon", "x0": 200, "x1": 240, "top": 30, "bottom": 32},
                        {"text": "Data", "x0": 300, "x1": 325, "top": 30, "bottom": 32},
                        {"text": "urodzenia", "x0": 330, "x1": 385, "top": 30, "bottom": 32},
                        {"text": "Email", "x0": 430, "x1": 455, "top": 30, "bottom": 32},
                        {"text": "Adres", "x0": 520, "x1": 545, "top": 30, "bottom": 32},
                        {"text": "Kod", "x0": 640, "x1": 660, "top": 30, "bottom": 32},
                        {"text": "pocztowy", "x0": 665, "x1": 715, "top": 30, "bottom": 32},
                        {"text": "08:30", "x0": 10, "x1": 35, "top": 40, "bottom": 42},
                        {"text": "Anna", "x0": 80, "x1": 100, "top": 40, "bottom": 42},
                        {"text": "Nowak", "x0": 105, "x1": 135, "top": 40, "bottom": 42},
                        {"text": "+49111111111", "x0": 200, "x1": 255, "top": 40, "bottom": 42},
                        {"text": "01.01.1990", "x0": 300, "x1": 350, "top": 40, "bottom": 42},
                        {"text": "anna@example.com", "x0": 430, "x1": 500, "top": 40, "bottom": 42},
                        {"text": "Main", "x0": 520, "x1": 545, "top": 40, "bottom": 42},
                        {"text": "1", "x0": 548, "x1": 552, "top": 40, "bottom": 42},
                        {"text": "10115", "x0": 640, "x1": 665, "top": 40, "bottom": 42},
                        {"text": "09:00", "x0": 10, "x1": 35, "top": 50, "bottom": 52},
                        {"text": "Jan", "x0": 80, "x1": 96, "top": 50, "bottom": 52},
                        {"text": "Kowalski", "x0": 105, "x1": 150, "top": 50, "bottom": 52},
                        {"text": "+49222222222", "x0": 200, "x1": 255, "top": 50, "bottom": 52},
                        {"text": "02.02.1985", "x0": 300, "x1": 350, "top": 50, "bottom": 52},
                        {"text": "jan@example.com", "x0": 430, "x1": 495, "top": 50, "bottom": 52},
                        {"text": "Side", "x0": 520, "x1": 545, "top": 50, "bottom": 52},
                        {"text": "2", "x0": 548, "x1": 552, "top": 50, "bottom": 52},
                        {"text": "10999", "x0": 640, "x1": 665, "top": 50, "bottom": 52},
                    ],
                )
            ]
        )

        with patch("apps.reception.pdf_import.pdfplumber.open", return_value=fake_pdf):
            parsed = parser.parse("dummy.pdf")

        self.assertEqual(parsed.clinic_name, "Berlin Central")
        self.assertEqual(parsed.import_date, date(2026, 3, 8))
        self.assertEqual(len(parsed.rows), 2)
        self.assertEqual(parsed.rows[0].full_name_raw, "Anna Nowak")

    def test_parse_rejects_unsupported_layout(self) -> None:
        parser = DoctolibPdfParser()
        fake_pdf = FakePdfDocument(
            [FakePdfPage(text="Unsupported content", words=[{"text": "Unsupported", "x0": 10, "x1": 50, "top": 10, "bottom": 12}])]
        )

        with patch("apps.reception.pdf_import.pdfplumber.open", return_value=fake_pdf):
            with self.assertRaises(PatientPdfImportFailure) as context:
                parser.parse("dummy.pdf")

        self.assertEqual(context.exception.error_code, PatientPdfImportErrorCode.PDF_UNSUPPORTED_LAYOUT)


class PatientPdfImportServiceTests(TestCase):
    def setUp(self) -> None:
        self.reception_user = StaffUser.objects.create_user(
            username="import-user",
            email="import-user@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")
        self.clinic = ClinicSite.objects.create(
            code="IMP",
            name="Import Clinic",
            pdf_import_shift_code="FULL_DAY",
        )
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic,
            code="IMP-R1",
            name="Import Room",
        )
        self.clinic.pdf_import_default_consulting_room = self.room
        self.clinic.save(update_fields=["pdf_import_default_consulting_room"])

    def _create_batch(self, source_file_name: str) -> PatientImportBatch:
        return PatientImportBatch.objects.create(
            source_file_name=source_file_name,
            source_file_sha256="a" * 64,
            created_by_user=self.reception_user,
        )

    def test_process_patient_pdf_import_batch_creates_patient_and_queue_entry(self) -> None:
        batch = self._create_batch("patients.pdf")
        parsed_import = ParsedPdfImport(
            import_date=date(2026, 3, 8),
            clinic_name=self.clinic.name,
            rows=(
                ParsedPatientRow(
                    row_number=1,
                    appointment_time_raw="08:30",
                    full_name_raw="Anna Nowak",
                    phone_raw="+49 111 111 111",
                    date_of_birth_raw="01.01.1990",
                    email_raw="anna@example.com",
                    address_raw="Main 1",
                    postal_code_raw="10115",
                ),
            ),
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(b"%PDF-1.4")
            temp_path = temp_file.name
        try:
            with patch("apps.reception.pdf_import.DoctolibPdfParser.parse", return_value=parsed_import):
                process_patient_pdf_import_batch(batch_id=batch.id, stored_file_path=temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportStatus.COMPLETED)
        self.assertEqual(batch.inserted_rows, 1)
        self.assertEqual(batch.error_rows, 0)
        self.assertTrue(Patient.objects.filter(first_name="Anna", last_name="Nowak").exists())
        self.assertEqual(QueueEntry.objects.count(), 1)

    def test_process_patient_pdf_import_batch_marks_duplicate_visit_as_error(self) -> None:
        first_batch = self._create_batch("patients-1.pdf")
        second_batch = self._create_batch("patients-2.pdf")
        parsed_import = ParsedPdfImport(
            import_date=date(2026, 3, 8),
            clinic_name=self.clinic.name,
            rows=(
                ParsedPatientRow(
                    row_number=1,
                    appointment_time_raw="08:30",
                    full_name_raw="Anna Nowak",
                    phone_raw="+49 111 111 111",
                    date_of_birth_raw="01.01.1990",
                    email_raw="anna@example.com",
                    address_raw="Main 1",
                    postal_code_raw="10115",
                ),
            ),
        )

        for batch in (first_batch, second_batch):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                temp_file.write(b"%PDF-1.4")
                temp_path = temp_file.name
            try:
                with patch("apps.reception.pdf_import.DoctolibPdfParser.parse", return_value=parsed_import):
                    process_patient_pdf_import_batch(batch_id=batch.id, stored_file_path=temp_path)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        second_batch.refresh_from_db()
        self.assertEqual(second_batch.status, ImportStatus.COMPLETED_WITH_ERRORS)
        self.assertEqual(second_batch.inserted_rows, 0)
        self.assertEqual(second_batch.error_rows, 1)
        self.assertEqual(
            PatientImportError.objects.get(batch=second_batch).error_code,
            PatientPdfImportErrorCode.DUPLICATE_VISIT,
        )


class DailyQueueAdminImportTests(TestCase):
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
        self.assertContains(response, reverse("admin:reception_dailyqueue_import_pdf"))

    def test_import_pdf_admin_view_enqueues_batch(self) -> None:
        batch = PatientImportBatch.objects.create(
            source_file_name="patients.pdf",
            source_file_sha256="b" * 64,
            created_by_user=self.admin_user,
        )
        with patch("apps.reception.admin.enqueue_patient_pdf_import", return_value=batch) as enqueue_mock:
            response = self.client.post(
                reverse("admin:reception_dailyqueue_import_pdf"),
                data={
                    "file": SimpleUploadedFile("patients.pdf", b"%PDF-1.4"),
                    "next": reverse("admin:reception_dailyqueue_changelist"),
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:reception_dailyqueue_changelist"))
        enqueue_mock.assert_called_once()
