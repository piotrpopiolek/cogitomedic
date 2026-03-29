from __future__ import annotations

import json
from uuid import uuid4

from django.contrib.auth.models import Group
from django.test import Client, TestCase

from apps.core.api_utils import assign_group_to_test_user
from apps.operations.models import AuditEvent
from apps.reception.models import TabletDevice
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
        success_ev = AuditEvent.objects.filter(
            event_type="STAFF_AUTH_LOGIN_SUCCESS", actor_user_id=self.user.id
        ).first()
        self.assertIsNotNone(success_ev)
        self.assertIn("client_ip", success_ev.metadata)

        me_response = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["user"]["username"], "auth-user")

        logout_response = self.client.post(
            "/api/v1/auth/logout", data="{}", content_type="application/json"
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertTrue(logout_response.json()["ok"])
        logout_ev = AuditEvent.objects.filter(
            event_type="STAFF_AUTH_LOGOUT", actor_user_id=self.user.id
        ).first()
        self.assertIsNotNone(logout_ev)

        me_after_logout = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_after_logout.status_code, 401)

    def test_login_invalid_credentials(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": "auth-user", "password": "wrong-password"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        fail_ev = (
            AuditEvent.objects.filter(event_type="STAFF_AUTH_LOGIN_FAILED")
            .order_by("-event_time")
            .first()
        )
        self.assertIsNotNone(fail_ev)
        self.assertEqual(fail_ev.metadata.get("reason"), "invalid_credentials")
        self.assertEqual(fail_ev.metadata.get("username"), "auth-user")

    def test_login_rate_limit_returns_429(self) -> None:
        """After 5 POSTs to login per IP per minute, the 6th returns 429."""
        isolated_ip = "203.0.113.55"
        for _ in range(5):
            self.client.post(
                "/api/v1/auth/login",
                data=json.dumps({"username": "auth-user", "password": "wrong"}),
                content_type="application/json",
                REMOTE_ADDR=isolated_ip,
            )
        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"username": "auth-user", "password": "wrong"}),
            content_type="application/json",
            REMOTE_ADDR=isolated_ip,
        )
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.json().get("error"))


class AuthLoginAndroidIdTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.tablet_user = StaffUser.objects.create_user(
            username="tablet-auth-android",
            email="tablet-auth-android@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(self.tablet_user, "Tablet")
        self.device = TabletDevice.objects.create(
            android_id="api-login-android-seen",
            is_active=True,
        )

    def test_login_with_android_id_sets_device_last_seen_at(self) -> None:
        self.assertIsNone(self.device.last_seen_at)
        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {
                    "username": "tablet-auth-android",
                    "password": "safe-password",
                    "android_id": "api-login-android-seen",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_seen_at)

    def test_login_with_android_id_ignored_for_doctor(self) -> None:
        doctor = StaffUser.objects.create_user(
            username="doctor-auth-android",
            email="doctor-auth-android@example.com",
            password="safe-password",
            is_staff=True,
        )
        assign_group_to_test_user(doctor, "Doctor")
        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps(
                {
                    "username": "doctor-auth-android",
                    "password": "safe-password",
                    "android_id": "api-login-android-seen",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.device.refresh_from_db()
        self.assertIsNone(self.device.last_seen_at)


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

    def test_post_staff_user_creates_tablet_role_user(self) -> None:
        # Ensure group exists even if seed migration is not present in this test DB.
        assign_group_to_test_user(self.user, "Tablet")
        response = self.client.post(
            "/api/v1/staff-users",
            data=json.dumps(
                {
                    "username": "tablet2",
                    "email": "tablet2@example.com",
                    "first_name": "Tab",
                    "last_name": "Device",
                    "phone_number": "+49111222333",
                    "role": "TABLET",
                    "is_staff": True,
                    "is_active": True,
                    "password": "StrongPassword123!",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["role"], "TABLET")

    def test_post_staff_user_returns_400_when_group_for_role_is_missing(self) -> None:
        Group.objects.filter(name="Reception").delete()
        response = self.client.post(
            "/api/v1/staff-users",
            data=json.dumps(
                {
                    "username": "reception-missing-group",
                    "email": "reception.missing.group@example.com",
                    "first_name": "Maria",
                    "last_name": "NoGroup",
                    "role": "RECEPTION",
                    "is_staff": True,
                    "is_active": True,
                    "password": "StrongPassword123!",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

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

    def test_post_staff_user_invalid_preferred_locale_returns_400(self) -> None:
        response = self.client.post(
            "/api/v1/staff-users",
            data=json.dumps(
                {
                    "username": "bad-locale",
                    "email": "bad.locale@example.com",
                    "first_name": "Bad",
                    "last_name": "Locale",
                    "role": "DOCTOR",
                    "preferred_locale": "en-US",
                    "is_staff": True,
                    "is_active": True,
                    "password": "StrongPassword123!",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

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

    def test_patch_staff_user_invalid_preferred_locale_returns_400(self) -> None:
        response = self.client.patch(
            f"/api/v1/staff-users/{self.user.id}",
            data=json.dumps({"preferred_locale": "en-US"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

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
