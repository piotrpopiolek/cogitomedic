from __future__ import annotations

import uuid

from django.contrib.auth.models import Group
from django.db import transaction

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.users.models import StaffUser


def _get_required_role_group(*, role: str) -> Group:
    group_name = role.capitalize()
    group = Group.objects.filter(name=group_name).first()
    if group is None:
        raise DomainError(
            domain_message(
                "other.domain.staff_role_group_missing",
                role=role,
                group_name=group_name,
            ),
            api_message_key="other.domain.staff_role_group_missing",
            api_message_params={"role": role, "group_name": group_name},
        )
    return group


@transaction.atomic
def create_staff_user(
    *,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    role: str,
    password: str,
    phone_number: str | None = None,
    preferred_locale: str = "de-DE",
    is_staff: bool = True,
    is_active: bool = True,
) -> StaffUser:
    VALID_ROLES = {"DOCTOR", "RECEPTION", "ADMIN", "TABLET"}
    if role not in VALID_ROLES:
        raise DomainError(
            domain_message("other.domain.invalid_staff_role", role=role),
            api_message_key="other.domain.invalid_staff_role",
            api_message_params={"role": role},
        )

    user = StaffUser.objects.create_user(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
        phone_number=phone_number,
        preferred_locale=preferred_locale,
        is_staff=is_staff,
        is_active=is_active,
    )
    group = _get_required_role_group(role=role)
    user.groups.add(group)
    return user


@transaction.atomic
def update_staff_user(
    *,
    staff_user_id: uuid.UUID,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    phone_number: str | None = None,
    role: str | None = None,
    preferred_locale: str | None = None,
    is_staff: bool | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> StaffUser:
    user = StaffUser.objects.select_for_update().get(id=staff_user_id)
    update_fields: list[str] = []
    if email is not None:
        user.email = email
        update_fields.append("email")
    if first_name is not None:
        user.first_name = first_name
        update_fields.append("first_name")
    if last_name is not None:
        user.last_name = last_name
        update_fields.append("last_name")
    if phone_number is not None:
        user.phone_number = phone_number
        update_fields.append("phone_number")
    if role is not None:
        VALID_ROLES = {"DOCTOR", "RECEPTION", "ADMIN", "TABLET"}
        if role not in VALID_ROLES:
            raise DomainError(
                domain_message("other.domain.invalid_staff_role", role=role),
                api_message_key="other.domain.invalid_staff_role",
                api_message_params={"role": role},
            )
        group = _get_required_role_group(role=role)
        user.groups.clear()
        user.groups.add(group)
    if preferred_locale is not None:
        user.preferred_locale = preferred_locale
        update_fields.append("preferred_locale")
    if is_staff is not None:
        user.is_staff = is_staff
        update_fields.append("is_staff")
    if is_active is not None:
        user.is_active = is_active
        update_fields.append("is_active")
    if password is not None:
        user.set_password(password)
        update_fields.append("password")
    if not update_fields and role is None:
        raise DomainError(
            domain_message("other.api.provide_field_to_update"),
            api_message_key="other.api.provide_field_to_update",
        )
    if update_fields:
        user.save(update_fields=update_fields)
    return user


@transaction.atomic
def deactivate_staff_user(*, staff_user_id: uuid.UUID) -> StaffUser:
    user = StaffUser.objects.select_for_update().get(id=staff_user_id)
    if user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])
    return user
