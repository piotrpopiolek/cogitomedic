from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.models import Group
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.core.api_utils import assign_group_to_test_user
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

    def test_manager_has_no_add_or_delete_permission_on_staffuser(self) -> None:
        manager = StaffUser.objects.create_user(
            username="mgr-add-del",
            email="mgr-add-del@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(manager, "Manager")
        request = type("RequestStub", (), {"user": manager})()
        ma = StaffUserAdmin(StaffUser, admin.site)
        self.assertFalse(ma.has_add_permission(request))
        self.assertFalse(ma.has_delete_permission(request))

    def test_changelist_role_query_filters_by_doctor_group(self) -> None:
        """``?role=DOCTOR`` is applied in ``get_queryset`` (changelist may 302 in Unfold)."""
        doc = StaffUser.objects.create_user(
            username="role-filter-doc",
            email="role-filter-doc@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(doc, "Doctor")
        rec = StaffUser.objects.create_user(
            username="role-filter-rec",
            email="role-filter-rec@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(rec, "Reception")
        request = RequestFactory().get("/admin/users/staffuser/", {"role": "DOCTOR"})
        request.user = self.superuser
        ma = StaffUserAdmin(StaffUser, admin.site)
        qs = ma.get_queryset(request)
        usernames = set(qs.values_list("username", flat=True))
        self.assertIn("role-filter-doc", usernames)
        self.assertNotIn("role-filter-rec", usernames)
