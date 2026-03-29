"""Portal wyniki – OTP session for patient results access."""

from __future__ import annotations

import uuid

from django.db import models

from apps.core.translation_service import db_gettext_lazy


class PatientResultsOtpSession(models.Model):
    """
    OTP session for patient results portal. Created on request-otp, verified on verify-otp.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        "reception.Patient",
        on_delete=models.CASCADE,
        related_name="patient_results_otp_sessions",
        verbose_name=db_gettext_lazy("administration.field_patient", "Patient"),
    )
    phone = models.CharField(
        max_length=20,
        verbose_name=db_gettext_lazy("administration.field_phone", "Phone"),
    )
    otp_code_hash = models.CharField(
        max_length=64,
        verbose_name=db_gettext_lazy(
            "administration.field_otp_code_hash", "OTP code hash"
        ),
    )
    expires_at = models.DateTimeField(
        verbose_name=db_gettext_lazy("administration.field_expires_at", "Expires at")
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=db_gettext_lazy("administration.field_verified_at", "Verified at"),
    )
    verify_attempt_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=db_gettext_lazy(
            "administration.field_verify_attempt_count", "Verify attempt count"
        ),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )

    class Meta:
        db_table = "patient_results_otp_session"
        indexes = [
            models.Index(fields=["patient", "expires_at"]),
            models.Index(fields=["phone", "expires_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="patient_results_otp_expiry_after_created",
            ),
        ]

    def __str__(self) -> str:
        return f"OTP session {self.id} (patient={self.patient_id}, expires={self.expires_at})"
