from __future__ import annotations

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import StaffUser


class StaffUserAdminGroupsRequiredTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.superuser = StaffUser.objects.create_superuser(
            username="admin-groups",
            email="admin-groups@example.com",
            password="safe-password",
        )
        self.client.force_login(self.superuser)
        self.doctor_group, _ = Group.objects.get_or_create(name="Doctor")

    def test_add_user_without_groups_shows_validation_error(self) -> None:
        url = reverse("admin:users_staffuser_add")
        response = self.client.post(
            url,
            {
                "username": "new-staff",
                "email": "new-staff@example.com",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
                "first_name": "New",
                "last_name": "Staff",
                "preferred_locale": "de-DE",
                "is_staff": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StaffUser.objects.filter(username="new-staff").exists())
        # Required M2M: Django shows localized "field required" before clean_groups runs.
        self.assertContains(response, "id_groups_error")

    def test_add_user_with_group_succeeds(self) -> None:
        url = reverse("admin:users_staffuser_add")
        response = self.client.post(
            url,
            {
                "username": "new-staff-2",
                "email": "new-staff-2@example.com",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
                "first_name": "New",
                "last_name": "Staff",
                "preferred_locale": "de-DE",
                "is_staff": "on",
                "is_active": "on",
                "groups": [str(self.doctor_group.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        user = StaffUser.objects.get(username="new-staff-2")
        self.assertTrue(user.groups.filter(pk=self.doctor_group.pk).exists())

    def test_change_user_clearing_groups_shows_validation_error(self) -> None:
        user = StaffUser.objects.create_user(
            username="has-group",
            email="has-group@example.com",
            password="safe-password",
            first_name="Has",
            last_name="Group",
        )
        user.groups.add(self.doctor_group)
        url = reverse("admin:users_staffuser_change", args=[user.pk])
        response = self.client.post(
            url,
            {
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "preferred_locale": user.preferred_locale,
                "is_active": "on",
                "groups": [],
            },
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.groups.filter(pk=self.doctor_group.pk).exists())
