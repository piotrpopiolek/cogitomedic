from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.translation_service import db_gettext_lazy

ROLE_GROUP_NAME_MAP = {
    "DOCTOR": "Doctor",
    "RECEPTION": "Reception",
    "ADMIN": "Admin",
    "TABLET": "Tablet",
    "MANAGER": "Manager",
}
VALID_STAFF_ROLES = frozenset(ROLE_GROUP_NAME_MAP.keys())


class StaffUserPreferredLocale(models.TextChoices):
    DE_DE = "de-DE", db_gettext_lazy(
        "administration.choice_staff_locale_de_de", "German (Germany)"
    )
    EN_GB = "en-GB", db_gettext_lazy(
        "administration.choice_staff_locale_en_gb", "English (United Kingdom)"
    )
    PL_PL = "pl-PL", db_gettext_lazy(
        "administration.choice_staff_locale_pl_pl", "Polish (Poland)"
    )


class StaffUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    password = models.CharField(
        max_length=128,
        verbose_name=db_gettext_lazy("administration.field_password", "Password"),
    )
    username = models.CharField(
        max_length=150,
        unique=True,
        verbose_name=db_gettext_lazy("administration.field_username", "Username"),
    )
    first_name = models.CharField(
        max_length=50,
        verbose_name=db_gettext_lazy("administration.field_first_name", "First name"),
    )
    last_name = models.CharField(
        max_length=100,
        verbose_name=db_gettext_lazy("administration.field_last_name", "Last name"),
    )
    email = models.EmailField(
        unique=True, verbose_name=db_gettext_lazy("administration.field_email", "Email")
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=db_gettext_lazy(
            "administration.field_phone_number", "Phone number"
        ),
    )
    is_staff = models.BooleanField(
        default=False,
        verbose_name=db_gettext_lazy("administration.field_is_staff", "Is staff"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=db_gettext_lazy("administration.field_is_active", "Is active"),
    )
    date_joined = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_date_joined", "Date joined"),
    )
    code = models.CharField(
        max_length=50,
        default="",
        verbose_name=db_gettext_lazy("administration.field_code", "Code"),
    )
    preferred_locale = models.CharField(
        max_length=10,
        choices=StaffUserPreferredLocale.choices,
        default=StaffUserPreferredLocale.DE_DE,
        verbose_name=db_gettext_lazy(
            "administration.field_preferred_locale", "Preferred locale"
        ),
    )
    consulting_room = models.ForeignKey(
        "reception.ConsultingRoom",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="staff_users",
        verbose_name=db_gettext_lazy(
            "administration.field_consulting_room", "Consulting room"
        ),
    )
    clinic_sites = models.ManyToManyField(
        "reception.ClinicSite",
        db_table="staff_user_clinic_site",
        related_name="staff_users",
        blank=True,
        verbose_name=db_gettext_lazy(
            "administration.field_clinic_sites", "Clinic sites"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=db_gettext_lazy("administration.field_updated_at", "Updated at"),
    )

    class Meta:
        db_table = "staff_user"
        verbose_name = db_gettext_lazy("administration.model_staffuser", "Staff user")
        verbose_name_plural = db_gettext_lazy(
            "administration.model_staffuser_plural", "Staff users"
        )
        constraints = [
            models.CheckConstraint(
                condition=models.Q(phone_number__isnull=True)
                | models.Q(phone_number__regex=r"^[0-9+() -]{7,20}$"),
                name="staff_user_phone_format",
            )
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def _has_role_group(self, group_name: str) -> bool:
        return self.groups.filter(name=group_name).exists()

    @property
    def is_doctor(self) -> bool:
        return self._has_role_group(ROLE_GROUP_NAME_MAP["DOCTOR"])

    @property
    def is_reception(self) -> bool:
        return self._has_role_group(ROLE_GROUP_NAME_MAP["RECEPTION"])

    @property
    def is_admin_role(self) -> bool:
        return self._has_role_group(ROLE_GROUP_NAME_MAP["ADMIN"])

    @property
    def is_tablet(self) -> bool:
        return self._has_role_group(ROLE_GROUP_NAME_MAP["TABLET"])

    @property
    def is_manager(self) -> bool:
        return self._has_role_group(ROLE_GROUP_NAME_MAP["MANAGER"])
