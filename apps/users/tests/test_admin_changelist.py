from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.admin import StaffUserAdmin
from apps.users.models import StaffUser


class StaffUserAdminChangelistTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.superuser = StaffUser.objects.create_superuser(
            username="admin-changelist",
            email="admin-changelist@example.com",
            password="safe-password",
        )
        self.client.force_login(self.superuser)

    def test_single_edit_entrypoint_first_column(self) -> None:
        self.assertNotIn("edit_link", StaffUserAdmin.list_display)
        self.assertEqual(StaffUserAdmin.list_display_links, ("username",))
        self.assertIn("primary_role", StaffUserAdmin.list_display)
        self.assertIn("last_login_display", StaffUserAdmin.list_display)

    def test_changelist_has_no_duplicate_edit_button_column(self) -> None:
        StaffUser.objects.create_user(
            username="staff-a",
            email="staff-a@example.com",
            password="safe-password",
            first_name="A",
            last_name="User",
        )
        response = self.client.get(reverse("admin:users_staffuser_changelist"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('class="button">Edytuj</a>', content)

    def test_manager_cannot_access_staffuser_admin_changelist(self) -> None:
        manager = StaffUser.objects.create_user(
            username="manager-hidden",
            email="manager-hidden@example.com",
            password="safe-password",
            is_staff=True,
        )
        Group.objects.get_or_create(name="Manager")[0].user_set.add(manager)
        self.client.force_login(manager)

        response = self.client.get(reverse("admin:users_staffuser_changelist"))

        self.assertEqual(response.status_code, 403)

    def test_manager_has_no_staffuser_admin_module_permission(self) -> None:
        manager = StaffUser.objects.create_user(
            username="manager-module-hidden",
            email="manager-module-hidden@example.com",
            password="safe-password",
            is_staff=True,
        )
        Group.objects.get_or_create(name="Manager")[0].user_set.add(manager)

        request = type(
            "RequestStub",
            (),
            {"user": manager},
        )()

        self.assertFalse(
            StaffUserAdmin(StaffUser, admin.site).has_module_permission(request)
        )
