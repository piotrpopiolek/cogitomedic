"""Smoke tests for tablet views (login, home, queue, entry, form)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ObjectDoesNotExist
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
    TabletDevice,
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
            queue_date=timezone.localdate(),
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

    def test_login_post_ignores_unsafe_next_query_param(self):
        """``next`` is read from the query string; external URLs must not win redirects."""
        resp = self.client.post(
            "/tablet/login/?next=https://evil.example/phish",
            {"username": "tablet-smoke", "password": "x"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            resp.url.endswith("/tablet/") or resp.url.rstrip("/").endswith("/tablet")
        )

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
        self.assertContains(resp, "tablet-patient-identity")
        self.assertContains(resp, "Test, Smoke")
        self.assertContains(resp, "01.01.1990")
        self.assertContains(resp, "48500000001")
        self.assertContains(resp, "Bitte prüfen Sie Name, Geburtsdatum")


class TabletViewsScopeAndEdgeTests(TestCase):
    """Coverage for scope checks, device session, dates, and form edge cases in tablet_views."""

    def setUp(self) -> None:
        self.client = Client()
        self.tablet_user = StaffUser.objects.create_user(
            username="tablet-scope",
            email="tab-scope@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.tablet_user, "Tablet")
        self.clinic = ClinicSite.objects.create(code="TS", name="Tablet Scope Clinic")
        self.tablet_user.clinic_sites.add(self.clinic)
        room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="S1", name="S1"
        )
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        patient = Patient.objects.create(
            first_name="Scope",
            last_name="Patient",
            date_of_birth=date(1991, 2, 2),
            phone="+48500000002",
            email="scope@example.com",
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

    def _login_tablet(self) -> None:
        self.client.login(username="tablet-scope", password="x")

    def test_login_get_when_already_authenticated_redirects_home(self) -> None:
        self._login_tablet()
        resp = self.client.get("/tablet/login/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.endswith("/tablet/") or "/tablet/" in resp.url)

    def test_login_post_with_android_id_marks_device_unassigned_home(self) -> None:
        """Device auto-registered without clinic_site → empty queue list + tablet_unassigned."""
        aid = f"android-unassigned-{uuid4().hex[:12]}"
        resp = self.client.post(
            "/tablet/login/",
            {"username": "tablet-scope", "password": "x", "android_id": aid},
        )
        self.assertEqual(resp.status_code, 302)
        self._login_tablet()
        home = self.client.get("/tablet/")
        self.assertEqual(home.status_code, 200)
        self.assertTrue(home.context["tablet_unassigned"])

    def test_home_ignores_invalid_tablet_device_id_in_session(self) -> None:
        self._login_tablet()
        session = self.client.session
        session["tablet_device_id"] = "not-a-valid-uuid"
        session.save()
        home = self.client.get("/tablet/")
        self.assertEqual(home.status_code, 200)
        self.assertFalse(home.context["tablet_unassigned"])

    def test_logout_clears_tablet_device_id_from_session(self) -> None:
        aid = f"android-logout-{uuid4().hex[:12]}"
        self.client.post(
            "/tablet/login/",
            {"username": "tablet-scope", "password": "x", "android_id": aid},
        )
        self.assertIn("tablet_device_id", self.client.session)
        self.client.get("/tablet/logout/")
        self.assertNotIn("tablet_device_id", self.client.session)

    def test_login_get_invalid_locale_defaults_to_german(self) -> None:
        resp = self.client.get("/tablet/login/?locale=xx")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["staff_locale"], "de")

    def test_login_get_valid_locale_persists_in_session(self) -> None:
        self.client.get("/tablet/login/?locale=pl")
        self.assertEqual(self.client.session.get("tablet_staff_locale"), "pl")

    def test_queue_entries_html_returns_all_entries_when_more_than_fifty(self) -> None:
        """Regression: HTML list is unpaginated (unlike API limit default 50)."""
        room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="BLK", name="Bulk room"
        )
        queue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=self.clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        total = 55
        patients = [
            Patient(
                first_name=f"Q{index:03d}",
                last_name="Queue",
                date_of_birth=date(1988, 6, 15),
                phone=f"48510{index:06d}",
                email=f"queue-bulk-{index}@example.com",
            )
            for index in range(total)
        ]
        Patient.objects.bulk_create(patients)
        QueueEntry.objects.bulk_create(
            [
                QueueEntry(
                    daily_queue=queue,
                    patient=patients[index],
                    entry_status=QueueEntryStatus.WAITING,
                    position_no=index + 1,
                    created_by_user=self.tablet_user,
                )
                for index in range(total)
            ]
        )
        self._login_tablet()
        resp = self.client.get(f"/tablet/queue/{queue.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["entries"]), total)
        self.assertContains(resp, "1. Queue Q000")
        self.assertContains(resp, "55. Queue Q054")

    def test_queue_entries_not_today_returns_400(self) -> None:
        room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="S2", name="S2"
        )
        old_queue = DailyQueue.objects.create(
            queue_date=timezone.localdate() - timedelta(days=3),
            clinic_site=self.clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        self._login_tablet()
        resp = self.client.get(f"/tablet/queue/{old_queue.id}/")
        self.assertEqual(resp.status_code, 400)

    def test_queue_entries_forbidden_when_device_scoped_to_other_clinic(self) -> None:
        other = ClinicSite.objects.create(code="OT", name="Other Site")
        oroom = ConsultingRoom.objects.create(clinic_site=other, code="O1", name="O1")
        oqueue = DailyQueue.objects.create(
            queue_date=timezone.localdate(),
            clinic_site=other,
            consulting_room=oroom,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        aid = f"android-other-clinic-{uuid4().hex[:8]}"
        TabletDevice.objects.create(android_id=aid, is_active=True, clinic_site=other)
        self.client.post(
            "/tablet/login/",
            {"username": "tablet-scope", "password": "x", "android_id": aid},
        )
        self._login_tablet()
        resp = self.client.get(f"/tablet/queue/{self.queue.id}/")
        self.assertEqual(resp.status_code, 403)
        resp_ok = self.client.get(f"/tablet/queue/{oqueue.id}/")
        self.assertEqual(resp_ok.status_code, 200)

    def test_entry_start_not_today_returns_400(self) -> None:
        room = ConsultingRoom.objects.create(
            clinic_site=self.clinic, code="S3", name="S3"
        )
        old_queue = DailyQueue.objects.create(
            queue_date=timezone.localdate() - timedelta(days=1),
            clinic_site=self.clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.tablet_user,
        )
        old_entry = QueueEntry.objects.create(
            daily_queue=old_queue,
            patient=self.entry.patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=1,
            created_by_user=self.tablet_user,
        )
        self._login_tablet()
        resp = self.client.get(f"/tablet/entry/{old_entry.id}/")
        self.assertEqual(resp.status_code, 400)

    def test_entry_start_post_creates_session_and_renders_started(self) -> None:
        self._login_tablet()
        resp = self.client.post(
            f"/tablet/entry/{self.entry.id}/",
            {"tablet_device_id": "", "android_id": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tablet/entry_started.html")
        self.assertContains(resp, "/tablet/form/")

    def test_entry_start_post_invalid_tablet_device_uuid_still_creates_session(
        self,
    ) -> None:
        self._login_tablet()
        resp = self.client.post(
            f"/tablet/entry/{self.entry.id}/",
            {"tablet_device_id": "not-a-uuid", "android_id": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tablet/entry_started.html")

    def test_form_submitted_intake_renders_submitted_template(self) -> None:
        PatientIntakeForm.objects.filter(id=self.intake.id).update(
            form_status=IntakeStatus.SUBMITTED,
            submitted_at=timezone.now(),
            signature_sha256="a" * 64,
        )
        self._login_tablet()
        resp = self.client.get(f"/tablet/form/{self.intake.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tablet/form_submitted.html")

    def test_form_locale_query_updates_session_form_locale(self) -> None:
        self._login_tablet()
        self.client.get(f"/tablet/form/{self.intake.id}/?locale=en")
        self.intake.session.refresh_from_db()
        self.assertEqual(self.intake.session.form_locale, "en-GB")

    def test_entry_start_post_session_failure_returns_404(self) -> None:
        self._login_tablet()
        with patch(
            "cogitomedica.tablet_views.issue_tablet_session_latest_wins",
            side_effect=ObjectDoesNotExist(),
        ):
            resp = self.client.post(
                f"/tablet/entry/{self.entry.id}/",
                {"tablet_device_id": "", "android_id": ""},
            )
        self.assertEqual(resp.status_code, 404)
        self.assertTemplateUsed(resp, "tablet/error.html")

    def test_form_get_context_missing_returns_404(self) -> None:
        self._login_tablet()
        with patch(
            "cogitomedica.tablet_views.get_intake_form_context",
            side_effect=ObjectDoesNotExist(),
        ):
            resp = self.client.get(f"/tablet/form/{self.intake.id}/")
        self.assertEqual(resp.status_code, 404)
        self.assertTemplateUsed(resp, "tablet/error.html")
