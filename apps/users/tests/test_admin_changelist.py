from __future__ import annotations

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
