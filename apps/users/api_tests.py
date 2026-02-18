from __future__ import annotations

import json

from django.test import Client, TestCase

from apps.users.models import StaffRole, StaffUser


class UsersAuthApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = StaffUser.objects.create_user(
            username="auth-user",
            email="auth.user@example.com",
            password="safe-password",
            role=StaffRole.DOCTOR,
            is_staff=True,
        )

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
