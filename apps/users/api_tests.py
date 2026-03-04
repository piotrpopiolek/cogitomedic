from __future__ import annotations

import json

from uuid import uuid4

from django.test import Client, TestCase

from apps.core.api_utils import assign_group_to_test_user
from apps.users.models import StaffUser


class UsersAuthApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = StaffUser.objects.create_user(
            username="auth-user",
            email="auth.user@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.user, "Doctor")

    def test_login_and_me_and_logout_flow(self) -> None:
        login_response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": "auth-user", "password": "safe-password"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.json()
        self.assertEqual(login_payload["user"]["username"], "auth-user")
        self.assertEqual(login_payload["user"]["role"], "DOCTOR")

        me_response = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["user"]["username"], "auth-user")

        logout_response = self.client.post("/api/v1/auth/logout", data="{}", content_type="application/json")
        self.assertEqual(logout_response.status_code, 200)
        self.assertTrue(logout_response.json()["ok"])

        me_after_logout = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_after_logout.status_code, 401)

    def test_login_invalid_credentials(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": "auth-user", "password": "wrong-password"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_login_rate_limit_returns_429(self) -> None:
        """After 5 POSTs to login per IP per minute, the 6th returns 429."""
        for _ in range(5):
            self.client.post(
                "/api/v1/auth/login",
                data=json.dumps({"username": "auth-user", "password": "wrong"}),
                content_type="application/json",
            )
        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": "auth-user", "password": "wrong"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json().get("error"), "Too many requests. Try again later.")


class StaffUsersApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = StaffUser.objects.create_user(
            username="admin-user",
            email="admin.user@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.user, "Admin")
        self.client.force_login(self.user)

    def test_get_staff_users_returns_paginated_items(self) -> None:
        response = self.client.get("/api/v1/staff-users?page=1&page_size=20")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("items", payload)
        self.assertIn("pagination", payload)
        self.assertGreaterEqual(payload["pagination"]["total"], 1)

    def test_post_staff_user_creates_user(self) -> None:
        response = self.client.post(
            "/api/v1/staff-users",
            data=json.dumps(
                {
                    "username": "reception2",
                    "email": "r2@example.com",
                    "first_name": "Maria",
                    "last_name": "Klein",
                    "phone_number": "+49123456789",
                    "role": "RECEPTION",
                    "is_staff": True,
                    "is_active": True,
                    "password": "StrongPassword123!",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["username"], "reception2")
        self.assertEqual(payload["role"], "RECEPTION")

    def test_post_staff_user_duplicate_returns_409(self) -> None:
        response = self.client.post(
            "/api/v1/staff-users",
            data=json.dumps(
                {
                    "username": "admin-user",
                    "email": "admin.user@example.com",
                    "first_name": "Admin",
                    "last_name": "Dup",
                    "role": "ADMIN",
                    "is_staff": True,
                    "is_active": True,
                    "password": "StrongPassword123!",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_get_staff_user_detail(self) -> None:
        response = self.client.get(f"/api/v1/staff-users/{self.user.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "admin-user")

    def test_patch_staff_user_updates_fields(self) -> None:
        response = self.client.patch(
            f"/api/v1/staff-users/{self.user.id}",
            data=json.dumps({"first_name": "Updated", "role": "DOCTOR"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["first_name"], "Updated")
        self.assertEqual(payload["role"], "DOCTOR")

    def test_delete_staff_user_soft_deactivates(self) -> None:
        response = self.client.delete(f"/api/v1/staff-users/{self.user.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "User deactivated")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_staff_user_detail_not_found_returns_404(self) -> None:
        response = self.client.get(f"/api/v1/staff-users/{uuid4()}")
        self.assertEqual(response.status_code, 404)

    def test_staff_users_requires_authentication(self) -> None:
        self.client.logout()
        response = self.client.get("/api/v1/staff-users")
        self.assertEqual(response.status_code, 401)

    def test_staff_users_requires_admin_role(self) -> None:
        self.client.logout()
        doctor = StaffUser.objects.create_user(
            username="doctor-non-admin",
            email="doctor.non.admin@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(doctor, "Doctor")
        self.client.force_login(doctor)
        response = self.client.get("/api/v1/staff-users")
        self.assertEqual(response.status_code, 403)
