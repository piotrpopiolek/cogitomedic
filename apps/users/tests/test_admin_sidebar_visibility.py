from __future__ import annotations

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import StaffUser


class AdminSidebarVisibilityTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.password = "safe-password"
        self.admin_user = StaffUser.objects.create_user(
            username="sidebar-admin",
            email="sidebar-admin@example.com",
            password=self.password,
            is_staff=True,
        )
        Group.objects.get_or_create(name="Admin")[0].user_set.add(self.admin_user)

        self.manager_user = StaffUser.objects.create_user(
            username="sidebar-manager",
            email="sidebar-manager@example.com",
            password=self.password,
            is_staff=True,
        )
        Group.objects.get_or_create(name="Manager")[0].user_set.add(self.manager_user)

    def test_admin_index_shows_auth_and_staff_links_for_admin(self) -> None:
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin:users_staffuser_changelist"))
        self.assertContains(response, reverse("admin:auth_group_changelist"))

    def test_admin_index_hides_auth_and_staff_links_for_manager(self) -> None:
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("admin:users_staffuser_changelist"))
        self.assertNotContains(response, reverse("admin:auth_group_changelist"))
        self.assertContains(response, reverse("admin:reception_patient_changelist"))
        self.assertContains(response, reverse("admin:reception_dailyqueue_changelist"))
        self.assertContains(
            response, reverse("admin:reception_patientimporterror_changelist")
        )

    def test_manager_cannot_open_group_admin_direct_url(self) -> None:
        self.client.force_login(self.manager_user)

        response = self.client.get(reverse("admin:auth_group_changelist"))

        self.assertEqual(response.status_code, 403)
