from __future__ import annotations

from django.test import TestCase

from apps.users.display import staff_user_display_name
from apps.users.models import StaffUser


class StaffUserDisplayNameTests(TestCase):
    def test_none_returns_empty_string(self) -> None:
        self.assertEqual(staff_user_display_name(None), "")

    def test_username_fallback_when_names_blank(self) -> None:
        bare = StaffUser.objects.create_user(
            username="uonly",
            email="uonly@example.com",
            password="pwd",
            first_name="",
            last_name="",
            is_staff=True,
        )
        self.assertEqual(staff_user_display_name(bare), "uonly")

    def test_create_user_has_empty_professional_title_by_default(self) -> None:
        user = StaffUser.objects.create_user(
            username="no-title",
            email="no-title@example.com",
            password="pwd",
        )
        self.assertEqual(user.professional_title, "")
