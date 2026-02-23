from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class StaffRole(models.TextChoices):
    RECEPTION = "RECEPTION", "Reception"
    DOCTOR = "DOCTOR", "Doctor"
    ADMIN = "ADMIN", "Admin"
    TABLET = "TABLET", "Tablet (waiting room)"


class StaffUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    password = models.CharField(max_length=128)
    username = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    code = models.CharField(max_length=50, default="")
    role = models.CharField(
        max_length=20,
        choices=StaffRole.choices,
        default=StaffRole.RECEPTION,
    )
    preferred_locale = models.CharField(max_length=10, default="de-DE")
    consulting_room = models.ForeignKey(
        "reception.ConsultingRoom",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="staff_users",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "staff_user"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(phone_number__isnull=True)
                | models.Q(phone_number__regex=r"^[0-9+() -]{7,20}$"),
                name="staff_user_phone_format",
            )
        ]
