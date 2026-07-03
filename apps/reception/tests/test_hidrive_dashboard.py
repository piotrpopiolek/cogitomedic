"""Reception dashboard — HiDrive missing results and RBAC."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.integrations.hidrive.client import HiDriveTimeoutError
from apps.integrations.hidrive import client as hidrive_client
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.incoming_pdf_scan import IncomingMatchStatus
from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
)
from apps.reception.hidrive_dashboard import (
    HIDRIVE_RESULT_COHORT_DAYS,
    build_missing_hidrive_results_report,
)
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientFormSession,
    QueueEntry,
    QueueEntryStatus,
)
from apps.users.models import StaffUser


@override_settings(
    HIDRIVE_USE_MOCK="1",
    HIDRIVE_INCOMING_PATH="/incoming",
    HIDRIVE_DASHBOARD_TIMEOUT_SECONDS=8,
)
class ReceptionDashboardRbacTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.url = reverse("admin_reception_dashboard")
        self.password = "safe-password"

    def _staff(self, username: str, group: str) -> StaffUser:
        user = StaffUser.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(user, group)
        return user

    def test_reception_manager_admin_get_200(self) -> None:
        for group in ("Reception", "Manager", "Admin"):
            user = self._staff(f"dash-{group.lower()}", group)
            self.client.force_login(user)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200, group)

    def test_tablet_accounting_doctor_get_403(self) -> None:
        for group in ("Tablet", "Accounting", "Doctor"):
            user = self._staff(f"dash-block-{group.lower()}", group)
            self.client.force_login(user)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 403, group)


@override_settings(
    HIDRIVE_USE_MOCK="1",
    HIDRIVE_INCOMING_PATH="/incoming",
    HIDRIVE_DASHBOARD_TIMEOUT_SECONDS=8,
)
class HidriveDashboardReportTests(TestCase):
    def setUp(self) -> None:
        hidrive_client._MockHiDriveAdapter.reset_test_state()
        self.admin = StaffUser.objects.create_user(
            username="hidrive-dash-admin",
            email="hidrive-dash-admin@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.clinic = ClinicSite.objects.create(code="HDA", name="HiDrive Dash A")
        self.room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="HDA-1", name="Room 1"
        )

    def _create_candidate_entry(
        self,
        *,
        suffix: str,
        entry_status=QueueEntryStatus.PATIENT_COMPLETED,
        intake_status=IntakeStatus.SUBMITTED,
        queue_date=None,
        source_type=MedicalDocumentSourceType.DIGITAL_INTAKE,
        doc_status=MedicalDocStatus.DRAFT,
        create_document=True,
    ) -> QueueEntry:
        patient = Patient.objects.create(
            first_name=f"Pat{suffix}",
            last_name="Missing",
            date_of_birth=date(1990, 1, 1),
            phone=f"49000{suffix}",
            email=f"missing-{suffix}@example.com",
        )
        queue = DailyQueue.objects.create(
            queue_date=queue_date or timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=self.room,
            created_by_user=self.admin,
        )
        entry = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            position_no=1,
            entry_status=entry_status,
            created_by_user=self.admin,
        )
        session = PatientFormSession.objects.create(
            queue_entry=entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=2),
            created_by_user=self.admin,
        )
        PatientIntakeForm.objects.create(
            queue_entry=entry,
            session=session,
            form_status=intake_status,
            **(
                {
                    "submitted_at": timezone.now(),
                    "signature_sha256": "a" * 64,
                }
                if intake_status == IntakeStatus.SUBMITTED
                else {}
            ),
        )
        if create_document:
            MedicalDocument.objects.create(
                queue_entry=entry,
                intake_form=entry.intake_form,
                created_by_user=self.admin,
                source_type=source_type,
                status=doc_status,
            )
        return entry

    def test_report_lists_no_file_candidate(self) -> None:
        entry = self._create_candidate_entry(suffix="01")
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Unrelated.pdf",
                    "path": "/incoming/Unrelated.pdf",
                    "size": 1,
                }
            ],
        )
        report = build_missing_hidrive_results_report(self.admin)
        self.assertEqual(report.hidrive_status, IncomingMatchStatus.OK)
        self.assertEqual(report.total_row_count, 1)
        self.assertEqual(report.rows[0].queue_entry_id, entry.id)
        self.assertEqual(report.rows[0].match_status, IncomingMatchStatus.NO_FILE)

    def test_report_excludes_matched_patient(self) -> None:
        self._create_candidate_entry(suffix="02")
        hidrive_client._MockHiDriveAdapter.seed_listing(
            "/incoming",
            [
                {
                    "name": "Missing_Pat02.pdf",
                    "path": "/incoming/Missing_Pat02.pdf",
                    "size": 1,
                }
            ],
        )
        report = build_missing_hidrive_results_report(self.admin)
        self.assertEqual(report.total_row_count, 0)

    def test_report_hidrive_error_on_timeout(self) -> None:
        self._create_candidate_entry(suffix="03")
        with patch(
            "apps.reception.hidrive_dashboard.list_incoming_lab_pdf_rows",
            side_effect=HiDriveTimeoutError("timeout"),
        ):
            report = build_missing_hidrive_results_report(self.admin)
        self.assertEqual(report.hidrive_status, IncomingMatchStatus.HIDRIVE_ERROR)
        self.assertEqual(report.rows, [])

    def test_report_excludes_old_queue_entries(self) -> None:
        old_date = timezone.localdate() - timedelta(days=HIDRIVE_RESULT_COHORT_DAYS + 1)
        self._create_candidate_entry(suffix="04", queue_date=old_date)
        report = build_missing_hidrive_results_report(self.admin)
        self.assertEqual(report.total_row_count, 0)

    def test_dashboard_shows_hidrive_section_on_timeout(self) -> None:
        self._create_candidate_entry(suffix="05")
        client = Client()
        client.force_login(self.admin)
        with patch(
            "apps.reception.hidrive_dashboard.list_incoming_lab_pdf_rows",
            side_effect=HiDriveTimeoutError("timeout"),
        ):
            response = client.get(reverse("admin_reception_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fehlende HiDrive-Laborergebnisse")
        self.assertContains(response, "HiDrive ist nicht erreichbar")
