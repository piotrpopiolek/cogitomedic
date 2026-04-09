"""Smoke tests for intake HTML views (admin panel).

Covers: intake_documents_list_view, intake_document_detail_view.
Focuses on status codes, auth enforcement and role gating.
"""

from __future__ import annotations

from uuid import uuid4

from django.test import Client, TestCase

from apps.core.api_utils import assign_group_to_test_user
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
