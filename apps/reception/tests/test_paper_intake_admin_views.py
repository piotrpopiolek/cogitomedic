from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.api_utils import assign_group_to_test_user
from apps.medical.models import PaperIntakeAuthorization
from apps.reception import paper_intake_admin_views as paper_intake_views
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    QueueEntry,
    QueueEntryStatus,
    QueueStatus,
)
from apps.users.models import StaffUser

_AUTH_REASON = (
    "Authorization reason text for paper intake admin view test (long enough)."
)


class PaperIntakeAdminViewsTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.reception = StaffUser.objects.create_user(
            username="rec-paper-ui",
            email="rec.paper.ui@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.admin = StaffUser.objects.create_user(
            username="adm-paper-ui",
            email="adm.paper.ui@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.doctor = StaffUser.objects.create_user(
            username="doc-paper-ui",
            email="doc.paper.ui@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

        clinic = ClinicSite.objects.create(code="PUI", name="Paper UI Clinic")
        room = ConsultingRoom.objects.create(clinic_site=clinic, code="P1", name="P1")
        self.queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=clinic,
            consulting_room=room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
            assigned_doctor=self.doctor,
        )
        patient = Patient.objects.create(
            first_name="Paper",
            last_name="UiPatient",
            date_of_birth=date(1991, 1, 1),
            phone="+48111222333",
            email="paper.ui@example.com",
        )
        self.entry = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception,
        )

    def test_hub_forbidden_for_doctor(self) -> None:
        self.client.force_login(self.doctor)
        r = self.client.get(reverse("admin_paper_intake_hub"))
        self.assertEqual(r.status_code, 403)

    def test_hub_forbidden_for_reception(self) -> None:
        """Paper intake hub is ADMIN/MANAGER only (same gate as ``ensure_admin_manager_staff``)."""
        self.client.force_login(self.reception)
        r = self.client.get(reverse("admin_paper_intake_hub"))
        self.assertEqual(r.status_code, 403)

    def test_hub_ok_for_admin(self) -> None:
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin_paper_intake_hub"))
        self.assertEqual(r.status_code, 200)

    def test_hub_pick_queryset_includes_only_waiting_in_window(self) -> None:
        busy = QueueEntry.objects.create(
            daily_queue=self.queue,
            patient=self.entry.patient,
            entry_status=QueueEntryStatus.IN_PROGRESS,
            position_no=2,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception,
        )
        qs = paper_intake_views._paper_intake_hub_queue_entries_queryset()
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.entry.id, ids)
        self.assertNotIn(busy.id, ids)

    def test_hub_redirects_with_queue_entry_pick(self) -> None:
        self.client.force_login(self.admin)
        r = self.client.get(
            reverse("admin_paper_intake_hub"),
            {"queue_entry": str(self.entry.id)},
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn(str(self.entry.id), r["Location"])

    def test_hub_redirects_with_legacy_queue_entry_id_param(self) -> None:
        self.client.force_login(self.admin)
        r = self.client.get(
            reverse("admin_paper_intake_hub"),
            {"queue_entry_id": str(self.entry.id)},
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn(str(self.entry.id), r["Location"])

    def test_post_authorize_creates_row(self) -> None:
        self.client.force_login(self.admin)
        url = reverse(
            "admin_paper_intake_entry", kwargs={"queue_entry_id": self.entry.id}
        )
        r = self.client.post(
            url,
            {"action": "authorize", "reason": _AUTH_REASON},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(
            PaperIntakeAuthorization.objects.filter(
                queue_entry_id=self.entry.id
            ).exists()
        )

    def test_entry_get_ok_for_manager_when_queue_entry_outside_assigned_clinics(
        self,
    ) -> None:
        """Paper intake entry is not clinic-scoped for MANAGER (oversight / hub parity)."""
        manager = StaffUser.objects.create_user(
            username="mgr-paper-scope",
            email="mgr.paper.scope@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(manager, "Manager")
        manager.clinic_sites.add(self.queue.clinic_site)

        other_clinic = ClinicSite.objects.create(code="PUO", name="Paper Other Clinic")
        other_room = ConsultingRoom.objects.create(
            clinic_site=other_clinic, code="O1", name="O1"
        )
        other_queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=other_clinic,
            consulting_room=other_room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
            assigned_doctor=self.doctor,
        )
        other_patient = Patient.objects.create(
            first_name="Other",
            last_name="SitePatient",
            date_of_birth=date(1992, 2, 2),
            phone="+48222333444",
            email="other.site@example.com",
        )
        entry_other = QueueEntry.objects.create(
            daily_queue=other_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception,
        )

        self.client.force_login(manager)
        url = reverse(
            "admin_paper_intake_entry", kwargs={"queue_entry_id": entry_other.id}
        )
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_entry_get_ok_for_manager_when_queue_entry_inside_assigned_clinic(
        self,
    ) -> None:
        manager = StaffUser.objects.create_user(
            username="mgr-paper-ok",
            email="mgr.paper.ok@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(manager, "Manager")
        manager.clinic_sites.add(self.queue.clinic_site)

        self.client.force_login(manager)
        url = reverse(
            "admin_paper_intake_entry", kwargs={"queue_entry_id": self.entry.id}
        )
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_hub_queryset_for_manager_includes_other_clinic_waiting_entries(
        self,
    ) -> None:
        """Hub list is not clinic-scoped; MANAGER with partial site assignment still sees all sites."""
        manager = StaffUser.objects.create_user(
            username="mgr-paper-hub",
            email="mgr.paper.hub@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(manager, "Manager")
        manager.clinic_sites.add(self.queue.clinic_site)
        self.client.force_login(manager)
        self.assertEqual(
            self.client.get(reverse("admin_paper_intake_hub")).status_code, 200
        )

        other_clinic = ClinicSite.objects.create(code="PUH", name="Paper Hub Other")
        other_room = ConsultingRoom.objects.create(
            clinic_site=other_clinic, code="H1", name="H1"
        )
        other_queue = DailyQueue.objects.create(
            queue_date=timezone.now().date(),
            clinic_site=other_clinic,
            consulting_room=other_room,
            status=QueueStatus.OPEN,
            created_by_user=self.reception,
            assigned_doctor=self.doctor,
        )
        other_patient = Patient.objects.create(
            first_name="Hub",
            last_name="OtherSite",
            date_of_birth=date(1993, 3, 3),
            phone="+48333444555",
            email="hub.other@example.com",
        )
        entry_other = QueueEntry.objects.create(
            daily_queue=other_queue,
            patient=other_patient,
            entry_status=QueueEntryStatus.WAITING,
            position_no=1,
            appointment_time=timezone.now() - timedelta(hours=4),
            created_by_user=self.reception,
        )

        qs = paper_intake_views._paper_intake_hub_queue_entries_queryset()
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.entry.id, ids)
        self.assertIn(entry_other.id, ids)

    def test_hub_invalid_pick_shows_error(self) -> None:
        self.client.force_login(self.admin)
        r = self.client.get(
            reverse("admin_paper_intake_hub"),
            {"queue_entry": str(uuid4())},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "bg-red-50")

    def test_hub_legacy_invalid_uuid_shows_error(self) -> None:
        self.client.force_login(self.admin)
        r = self.client.get(
            reverse("admin_paper_intake_hub"),
            {"queue_entry_id": "not-a-uuid"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "bg-red-50")

    def test_entry_post_invalid_action_shows_error(self) -> None:
        self.client.force_login(self.admin)
        url = reverse(
            "admin_paper_intake_entry", kwargs={"queue_entry_id": self.entry.id}
        )
        r = self.client.post(
            url,
            {"action": "nope", "reason": _AUTH_REASON},
        )
        self.assertEqual(r.status_code, 302)
        self.assertFalse(
            PaperIntakeAuthorization.objects.filter(
                queue_entry_id=self.entry.id
            ).exists()
        )

    def test_entry_post_authorize_domain_error_surfaces_message(self) -> None:
        self.client.force_login(self.admin)
        url = reverse(
            "admin_paper_intake_entry", kwargs={"queue_entry_id": self.entry.id}
        )
        r = self.client.post(
            url,
            {"action": "authorize", "reason": "short"},
        )
        self.assertEqual(r.status_code, 302)

    def test_entry_post_forbidden_for_doctor(self) -> None:
        self.client.force_login(self.doctor)
        url = reverse(
            "admin_paper_intake_entry", kwargs={"queue_entry_id": self.entry.id}
        )
        r = self.client.post(
            url,
            {"action": "authorize", "reason": _AUTH_REASON},
        )
        self.assertEqual(r.status_code, 403)
