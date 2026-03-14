"""Portal wyniki – OTP session for patient results access."""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


class PatientResultsOtpSession(models.Model):
    """
    OTP session for patient results portal. Created on request-otp, verified on verify-otp.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        "reception.Patient",
        on_delete=models.CASCADE,
        related_name="patient_results_otp_sessions",
    )
    phone = models.CharField(max_length=20)
    otp_code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    verify_attempt_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

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
