"""Admin changelist page-size switcher (all ModelAdmin modules)."""

from __future__ import annotations

from django.contrib import admin
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.core.api_utils import assign_group_to_test_user
from apps.core.admin_list_page_size import resolve_admin_list_page_size
from apps.core.constants import DEFAULT_LIST_LIMIT
from apps.operations.admin import AuditEventAdmin
from apps.operations.models import AuditEvent
from apps.users.models import StaffUser


class AdminChangelistPageSizeTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.admin_user = StaffUser.objects.create_superuser(
            username="admin-page-size",
            email="admin-page-size@example.com",
            password="x",
        )
        assign_group_to_test_user(self.admin_user, "Admin")
        self.client.force_login(self.admin_user)

    def test_resolve_admin_list_page_size_from_query(self) -> None:
        factory = RequestFactory()
        request = factory.get("/admin/operations/auditevent/", {"page_size": "10"})
        request.session = self.client.session
        self.assertEqual(resolve_admin_list_page_size(request), 10)

    def test_resolve_admin_list_page_size_invalid_falls_back(self) -> None:
        factory = RequestFactory()
        request = factory.get("/admin/operations/auditevent/", {"page_size": "25"})
        request.session = self.client.session
        self.assertEqual(resolve_admin_list_page_size(request), DEFAULT_LIST_LIMIT)

    def test_changelist_renders_page_size_links(self) -> None:
        response = self.client.get(
            reverse("admin:operations_auditevent_changelist"),
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("page_size=10", content)
        self.assertIn("page_size=100", content)
        self.assertIn("dark:bg-base-900", content)
        self.assertIn("dark:border-base-800", content)

    def test_changelist_page_size_query_limits_rows(self) -> None:
        for _ in range(15):
            AuditEvent.objects.create(event_type="TEST_PAGE_SIZE")
        response = self.client.get(
            reverse("admin:operations_auditevent_changelist"),
            {"page_size": "10"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["cl"].result_list), 10)

    def test_get_list_per_page_does_not_mutate_admin_singleton(self) -> None:
        factory = RequestFactory()
        request = factory.get(
            "/admin/operations/auditevent/",
            {"page_size": "10"},
        )
        request.session = self.client.session
        admin_instance = AuditEventAdmin(AuditEvent, admin.site)
        original_list_per_page = admin_instance.list_per_page
        self.assertEqual(admin_instance.get_list_per_page(request), 10)
        self.assertEqual(admin_instance.list_per_page, original_list_per_page)
