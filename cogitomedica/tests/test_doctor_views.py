"""Smoke tests for cogitomedica/doctor_views.py."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.external_pdf_service import GateResult
from apps.medical.models import MedicalDocStatus, MedicalDocument
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


class DoctorViewsSmokeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "test-pass"
        self.doctor = StaffUser.objects.create_user(
            username="doc",
            email="doc@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        self.reception_user = StaffUser.objects.create_user(
            username="rec",
            email="rec@example.com",
            password=self.password,
            is_staff=True,
        )
        assign_group_to_test_user(self.reception_user, "Reception")

    # -- helpers ------------------------------------------------

    def _login_doctor(self):
        self.client.force_login(self.doctor)

    # ==========================================================
    # Login
    # ==========================================================

    def test_login_get_returns_200(self):
        resp = self.client.get("/doctor/login/")
        self.assertEqual(resp.status_code, 200)

    def test_login_post_valid_doctor_redirects(self):
        resp = self.client.post(
            "/doctor/login/",
            {"username": "doc", "password": self.password},
        )
        self.assertEqual(resp.status_code, 302)

    # ==========================================================
    # Guard: anonymous and wrong role
    # ==========================================================

    def test_list_anonymous_redirects_to_login(self):
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_list_reception_user_redirects(self):
        self.client.force_login(self.reception_user)
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    # ==========================================================
    # List
    # ==========================================================

    def test_list_doctor_returns_200(self):
        self._login_doctor()
        resp = self.client.get("/doctor/")
        self.assertEqual(resp.status_code, 200)

    def test_list_lang_param_strips_and_redirects(self):
        self._login_doctor()
        resp = self.client.get("/doctor/?lang=pl")
        self.assertEqual(resp.status_code, 302)

    # ==========================================================
    # Logout
    # ==========================================================

    def test_logout_post_redirects_to_login(self):
        self._login_doctor()
        resp = self.client.post("/doctor/logout/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    # ==========================================================
    # Document detail – nonexistent UUID
    # ==========================================================

    def test_detail_nonexistent_returns_404(self):
        self._login_doctor()
        url = f"/doctor/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    # ==========================================================
    # Open by queue – nonexistent UUID
    # ==========================================================

    def test_open_by_queue_nonexistent_returns_error(self):
        self._login_doctor()
        url = f"/doctor/open/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


class DoctorDetailHappyPathTests(TestCase):
    """Full data chain for the document detail view."""

    def setUp(self):
        self.client = Client()
        self.doctor = StaffUser.objects.create_user(
            username="hp-doc",
            email="hp-doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        rec = StaffUser.objects.create_user(
            username="hp-rec",
            email="hp-rec@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")

        clinic = ClinicSite.objects.create(code="HP", name="HP Clinic")
        room = ConsultingRoom.objects.create(
            clinic_site=clinic, code="R1", name="Room 1"
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            assigned_doctor=self.doctor,
            created_by_user=rec,
        )
        patient = Patient.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            date_of_birth=date(1985, 6, 15),
            phone="+48500100200",
            email="jan@example.com",
        )
        qe = QueueEntry.objects.create(
            daily_queue=queue,
            patient=patient,
            entry_status=QueueEntryStatus.PATIENT_COMPLETED,
            position_no=1,
            created_by_user=rec,
        )
        sess = PatientFormSession.objects.create(
            queue_entry=qe,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=rec,
        )
        intake = PatientIntakeForm.objects.create(
            queue_entry=qe,
            session=sess,
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
            body_map_data=[
                {"x": 0.22, "y": 0.35, "side": "front"},
                {"x": 0.72, "y": 0.4, "side": "back"},
            ],
        )
        self.doc = MedicalDocument.objects.create(
            queue_entry=qe,
            intake_form=intake,
            status=MedicalDocStatus.DRAFT,
            current_version_no=0,
            created_by_user=self.doctor,
        )
        # Default HiDrive /incoming listing is empty in tests → real gate returns 422.
        gate_patcher = patch(
            "cogitomedica.doctor_views.check_external_pdf_gate",
            return_value=GateResult(
                True,
                (),
                None,
                skip_attachment_sync=False,
            ),
        )
        gate_patcher.start()
        self.addCleanup(gate_patcher.stop)

    def test_detail_happy_path_returns_200(self):
        self.client.force_login(self.doctor)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    @patch("cogitomedica.doctor_views.check_external_pdf_gate")
    def test_detail_shows_hidrive_soft_warning_banner(
        self, mock_gate: MagicMock
    ) -> None:
        """Non-blocking HiDrive outage: gate passes but UI shows translated warning."""
        mock_gate.return_value = GateResult(
            True,
            (),
            "HiDrive folder read failed (test).",
            skip_attachment_sync=True,
        )
        self.client.force_login(self.doctor)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("HiDrive folder read failed (test).", resp.content.decode())

    def test_detail_panel_includes_body_map_image_url_and_stored_points(self):
        self.client.force_login(self.doctor)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        m = re.search(
            r'<script[^>]*id="doctor-panel-data"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(m)
        panel = json.loads(m.group(1))
        self.assertIn("bodyMapImageUrl", panel)
        self.assertIn("tablet/body.jpg", panel["bodyMapImageUrl"])
        pts = panel["context"]["intake_summary"]["body_map_data"]
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0]["side"], "front")

    def test_detail_returns_423_when_locked_by_another_doctor(self):
        other = StaffUser.objects.create_user(
            username="hp-doc-2",
            email="hp-doc-2@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        dq = self.doc.queue_entry.daily_queue
        dq.assigned_doctor = other
        dq.save(update_fields=["assigned_doctor", "updated_at"])
        self.doc.locked_by_user = self.doctor
        self.doc.locked_at = timezone.now()
        self.doc.save(update_fields=["locked_by_user", "locked_at", "updated_at"])

        self.client.force_login(other)
        url = f"/doctor/{self.doc.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 423)

    def test_second_doctor_can_open_draft_without_queue_assignment(self):
        dq = self.doc.queue_entry.daily_queue
        dq.assigned_doctor = None
        dq.save(update_fields=["assigned_doctor", "updated_at"])
        other = StaffUser.objects.create_user(
            username="hp-doc-shared",
            email="hp-doc-shared@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(other, "Doctor")
        self.client.force_login(other)
        resp = self.client.get(f"/doctor/{self.doc.id}/")
        self.assertEqual(resp.status_code, 200)
