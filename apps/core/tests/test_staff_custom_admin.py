from __future__ import annotations

import uuid
from http import HTTPStatus

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.core.api_utils import assign_group_to_test_user
from apps.core.staff_custom_admin import (
    ensure_admin_manager_staff,
    ensure_clinic_site_visible_to_staff_user,
    is_admin_or_manager_staff,
)
from apps.users.models import StaffUser


class StaffCustomAdminAccessTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.admin = StaffUser.objects.create_user(
            username="sca-admin",
            email="sca.admin@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.admin, "Admin")
        self.manager = StaffUser.objects.create_user(
            username="sca-mgr",
            email="sca.mgr@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.manager, "Manager")
        self.doctor = StaffUser.objects.create_user(
            username="sca-doc",
            email="sca.doc@example.com",
            password="x",
            is_staff=True,
        )
        assign_group_to_test_user(self.doctor, "Doctor")

    def test_is_admin_or_manager_staff(self) -> None:
        self.assertTrue(is_admin_or_manager_staff(self.admin))
        self.assertTrue(is_admin_or_manager_staff(self.manager))
        self.assertFalse(is_admin_or_manager_staff(self.doctor))
        self.assertFalse(is_admin_or_manager_staff(AnonymousUser()))

    def test_ensure_admin_manager_staff_none_for_admin(self) -> None:
        request = self.factory.get("/")
        request.user = self.admin
        self.assertIsNone(ensure_admin_manager_staff(request))

    def test_ensure_admin_manager_staff_403_for_doctor(self) -> None:
        request = self.factory.get("/")
        request.user = self.doctor
        resp = ensure_admin_manager_staff(request)
        self.assertIsNotNone(resp)
        assert resp is not None
        self.assertEqual(resp.status_code, HTTPStatus.FORBIDDEN)

    def test_ensure_clinic_site_none_for_admin(self) -> None:
        request = self.factory.get("/")
        request.user = self.admin
        site_id = uuid.uuid4()
        self.assertIsNone(ensure_clinic_site_visible_to_staff_user(request, site_id))

    def test_ensure_clinic_site_403_when_manager_not_assigned(self) -> None:
        request = self.factory.get("/")
        request.user = self.manager
        foreign_site = uuid.uuid4()
        resp = ensure_clinic_site_visible_to_staff_user(request, foreign_site)
        self.assertIsNotNone(resp)
        assert resp is not None
        self.assertEqual(resp.status_code, HTTPStatus.FORBIDDEN)
