"""Smoke tests for intake HTML views (admin panel).

Covers: intake_documents_list_view, intake_document_detail_view.
Focuses on status codes, auth enforcement and role gating.
"""

from __future__ import annotations

from uuid import uuid4

from django.test import Client, RequestFactory, TestCase

from apps.core.api_utils import assign_group_to_test_user
from apps.intake.views import (
    _enrich_intake_document_list_items_for_display,
    _intake_pdf_status_display,
)
from apps.users.models import StaffUser

LIST_URL = "/admin/intake-documents/"


def _detail_url(version_id):
    return f"/admin/intake-documents/{version_id}/"


class IntakeDocumentsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.reception = StaffUser.objects.create_user(
            username="iv-rec",
            email="iv-rec@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.reception, "Reception")
        self.doctor = StaffUser.objects.create_user(
            username="iv-doc",
            email="iv-doc@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")
        self.admin = StaffUser.objects.create_user(
            username="iv-admin",
            email="iv-admin@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.manager = StaffUser.objects.create_user(
            username="iv-mgr",
            email="iv-mgr@ex.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.manager, "Manager")

    # -- list view auth ---------------------------------------------------

    def test_list_anonymous_redirects_to_login(self):
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp.url)

    def test_list_doctor_redirects_to_admin_index(self):
        self.client.login(username="iv-doc", password="x")
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/", resp.url)

    def test_list_reception_ok(self):
        self.client.login(username="iv-rec", password="x")
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_list_admin_ok(self):
        self.client.login(username="iv-admin", password="x")
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)

    def test_list_manager_ok(self):
        self.client.login(username="iv-mgr", password="x")
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, 200)

    # -- detail view -------------------------------------------------------

    def test_detail_nonexistent_uuid_returns_404(self):
        self.client.login(username="iv-rec", password="x")
        resp = self.client.get(_detail_url(uuid4()))
        self.assertEqual(resp.status_code, 404)

    def test_detail_anonymous_redirects_to_login(self):
        resp = self.client.get(_detail_url(uuid4()))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp.url)

    def test_detail_doctor_redirects_to_admin_index(self):
        self.client.login(username="iv-doc", password="x")
        resp = self.client.get(_detail_url(uuid4()))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/", resp.url)

    def test_detail_manager_nonexistent_uuid_returns_404(self):
        self.client.login(username="iv-mgr", password="x")
        resp = self.client.get(_detail_url(uuid4()))
        self.assertEqual(resp.status_code, 404)


class IntakeDocumentsListDisplayTests(TestCase):
    def test_pdf_status_display_uses_admin_translation_fallback(self):
        request = RequestFactory().get("/admin/intake-documents/")
        self.assertEqual(
            _intake_pdf_status_display(request, "COMPLETED"),
            "Wygenerowany",
        )
        self.assertEqual(
            _intake_pdf_status_display(request, "PROCESSING"),
            "W trakcie",
        )

    def test_enrich_list_items_adds_status_display(self):
        request = RequestFactory().get("/admin/intake-documents/")
        items = [{"pdf_generation_status": "FAILED"}]
        _enrich_intake_document_list_items_for_display(request, items)
        self.assertEqual(items[0]["pdf_generation_status_display"], "Błąd")
