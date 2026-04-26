"""Coverage for ``_get_required_role_group`` edge cases."""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.test import TestCase

from apps.core.exceptions import DomainError
from apps.users import services as users_services
from apps.users.models import ROLE_GROUP_NAME_MAP


class GetRequiredRoleGroupTests(TestCase):
    def tearDown(self) -> None:
        Group.objects.get_or_create(name=ROLE_GROUP_NAME_MAP["DOCTOR"])

    def test_raises_domain_error_when_role_not_in_role_map(self) -> None:
        """Defensive path: role string missing from ``ROLE_GROUP_NAME_MAP``."""
        bogus = "NOT_A_ROLE_IN_MAP"
        self.assertNotIn(bogus, ROLE_GROUP_NAME_MAP)
        with self.assertRaises(DomainError) as ctx:
            users_services._get_required_role_group(role=bogus)
        self.assertEqual(
            ctx.exception.api_message_key, "other.domain.invalid_staff_role"
        )

    def test_raises_when_auth_group_row_missing(self) -> None:
        """Group name from map exists but ``auth_group`` row was deleted."""
        role = "DOCTOR"
        group_name = ROLE_GROUP_NAME_MAP[role]
        Group.objects.filter(name=group_name).delete()
        with self.assertRaises(DomainError) as ctx:
            users_services._get_required_role_group(role=role)
        self.assertEqual(
            ctx.exception.api_message_key, "other.domain.staff_role_group_missing"
        )
