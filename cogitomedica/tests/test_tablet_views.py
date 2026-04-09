"""Smoke tests for tablet views (login, home, queue, entry, form)."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.models import IntakeStatus, PatientIntakeForm
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


class TabletViewsSmokeTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.tablet_user = StaffUser.objects.create_user(
            username="tablet-smoke",
            email="tab@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.tablet_user, "Tablet")

        self.doctor_user = StaffUser.objects.create_user(
            username="doctor-smoke",
            email="doc@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor_user, "Doctor")

        self.clinic = ClinicSite.objects.create(code="TC", name="Tablet Clinic")
        self.tablet_user.clinic_sites.add(self.clinic)

        room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="T1", name="T1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=self.clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        patient = Patient.objects.create(
            first_name="Smoke",
            last_name="Test",
            date_of_birth=date(1990, 1, 1),
            phone="+48500000001",
            email="smoke@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=1,
            created_by_user=self.tablet_user,
        )
        sess = PatientFormSession.objects.create(
            queue_entry=self.entry,
            form_locale="de-DE",
            expires_at=timezone.now() + timedelta(hours=1),
            created_by_user=self.tablet_user,
        )
        self.intake = PatientIntakeForm.objects.create(
            queue_entry=self.entry,
            session=sess,
            form_status=IntakeStatus.IN_PROGRESS,
        )

    # -- helpers ------------------------------------------------

    def _login_tablet(self):
        self.client.login(username="tablet-smoke", password="x")

    def _login_doctor(self):
        self.client.login(username="doctor-smoke", password="x")

    # -- login --------------------------------------------------

    def test_login_get_returns_200(self):
        resp = self.client.get("/tablet/login/")
        self.assertEqual(resp.status_code, 200)

    def test_login_post_tablet_user_redirects(self):
        resp = self.client.post(
            "/tablet/login/",
            {"username": "tablet-smoke", "password": "x"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/tablet/", resp.url)

    def test_login_post_doctor_stays_on_login(self):
        resp = self.client.post(
            "/tablet/login/",
            {"username": "doctor-smoke", "password": "x"},
        )
        self.assertEqual(resp.status_code, 200)

    # -- guard (anonymous) --------------------------------------

    def test_home_anonymous_redirects_to_login(self):
        resp = self.client.get("/tablet/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    # -- home (authenticated) -----------------------------------

    def test_home_tablet_user_returns_200(self):
        self._login_tablet()
        resp = self.client.get("/tablet/")
        self.assertEqual(resp.status_code, 200)

    # -- logout -------------------------------------------------

    def test_logout_redirects_to_login(self):
        self._login_tablet()
        resp = self.client.get("/tablet/logout/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    # -- queue entries (nonexistent) ----------------------------

    def test_queue_entries_nonexistent_returns_404(self):
        self._login_tablet()
        url = f"/tablet/queue/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    # -- queue entries (happy path) -----------------------------

    def test_queue_entries_existing_returns_200(self):
        self._login_tablet()
        url = f"/tablet/queue/{self.queue.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    # -- entry start (nonexistent) ------------------------------

    def test_entry_start_nonexistent_returns_404(self):
        self._login_tablet()
        url = f"/tablet/entry/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    # -- entry start (happy path) -------------------------------

    def test_entry_start_existing_returns_200(self):
        self._login_tablet()
        url = f"/tablet/entry/{self.entry.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    # -- form (nonexistent) -------------------------------------

    def test_form_nonexistent_returns_404(self):
        self._login_tablet()
        url = f"/tablet/form/{uuid4()}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    # -- form (happy path) --------------------------------------

    def test_form_existing_returns_200(self):
        self._login_tablet()
        url = f"/tablet/form/{self.intake.id}/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
