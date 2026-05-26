"""Portal wyniki – OTP request/verify services."""

from __future__ import annotations

import hashlib
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integrations.sms.client import get_sms_adapter
from apps.patient_results.constants import (
    OTP_MAX_VERIFY_ATTEMPTS,
    OTP_RATE_LIMIT_PER_HOUR,
    OTP_VALID_MINUTES,
)
from apps.patient_results.models import PatientResultsOtpSession
from apps.reception.patient_identity import (
    portal_identity_is_ambiguous,
    resolve_patient_for_portal,
)
from apps.reception.phone_utils import infer_sms_region_from_phone, normalize_phone

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from django.http import HttpRequest

# Simple OTP SMS template (DE default) – no DB translation for Phase 2 to avoid migration dependency
_DEFAULT_OTP_SMS = "CogitoMed: Ihr Code lautet {otp}"


def _hash_otp(otp_code: str) -> str:
    pepper = getattr(settings, "PATIENT_RESULTS_OTP_PEPPER", "") or ""
    payload = f"{pepper}{otp_code.strip()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _verify_captcha(captcha_token: str) -> bool:
    """Verify CAPTCHA token (Turnstile). Returns True if valid or skipped."""
    if getattr(settings, "CAPTCHA_VERIFY_SKIP", False):
        return True
    token = (captcha_token or "").strip()
    if not token:
        return False
    secret = getattr(settings, "TURNSTILE_SECRET_KEY", "") or ""
    if not secret:
        return False
    try:
        resp = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": token},
            timeout=10,
        )
        data = resp.json()
        return bool(data.get("success"))
    except Exception:
        logger.warning("CAPTCHA verify failed", exc_info=True)
        return False


def _get_otp_sms_text(otp_code: str, locale: str | None = None) -> str:
    """Return SMS text for OTP code (simple template for Phase 2)."""
    return _DEFAULT_OTP_SMS.format(otp=otp_code)


@dataclass(frozen=True)
class RequestOtpResult:
    """Result of request_otp. status='ok' when accepted; error set when CAPTCHA fails."""

    status: str  # "ok" | "captcha_failed"
    error: str | None = None  # "captcha_failed" when CAPTCHA invalid
    audit_outcome: str = (
        "silent_no_op"  # sms_sent | silent_no_op | captcha_failed | ambiguous_identity
    )
    patient_id: uuid.UUID | None = None  # set when SMS was sent (audit only)
    needs_last_name: bool = False


@dataclass(frozen=True)
class VerifyOtpResult:
    """Result of verify_otp."""

    success: bool
    patient_id: str | None = None
    error: str | None = None


def request_otp(
    phone: str,
    date_of_birth: date,
    captcha_token: str,
    last_name: str | None = None,
) -> RequestOtpResult:
    """
    Request OTP for patient results. Sends SMS if patient exists.
    Always returns success-like response to prevent enumeration.
    """
    if not _verify_captcha(captcha_token):
        return RequestOtpResult(
            status="captcha_failed",
            error="captcha_failed",
            audit_outcome="captcha_failed",
        )

    if len(normalize_phone(phone)) < 7:
        return RequestOtpResult(status="ok", audit_outcome="silent_no_op")

    patient = resolve_patient_for_portal(phone, date_of_birth, last_name)
    if patient is None:
        if portal_identity_is_ambiguous(phone, date_of_birth, last_name):
            return RequestOtpResult(
                status="ok",
                audit_outcome="ambiguous_identity",
                needs_last_name=True,
            )
        return RequestOtpResult(status="ok", audit_outcome="silent_no_op")

    # Rate limit per patient (not raw input digits — formats share one bucket).
    since = timezone.now() - timedelta(hours=1)
    recent_count = PatientResultsOtpSession.objects.filter(
        patient_id=patient.id,
        created_at__gte=since,
    ).count()
    if recent_count >= OTP_RATE_LIMIT_PER_HOUR:
        return RequestOtpResult(status="ok", audit_outcome="silent_no_op")

    pepper = (getattr(settings, "PATIENT_RESULTS_OTP_PEPPER", "") or "").strip()
    environment = (getattr(settings, "ENVIRONMENT", "dev") or "dev").strip().lower()
    if not pepper and environment != "dev":
        raise ValueError(
            "PATIENT_RESULTS_OTP_PEPPER must be set outside development environments."
        )

    otp_code = f"{random.randint(100000, 999999)}"
    otp_hash = _hash_otp(otp_code)
    expires_at = timezone.now() + timedelta(minutes=OTP_VALID_MINUTES)

    with transaction.atomic():
        PatientResultsOtpSession.objects.create(
            patient=patient,
            phone=patient.phone,
            otp_code_hash=otp_hash,
            expires_at=expires_at,
        )
        sms_text = _get_otp_sms_text(otp_code)
        adapter = get_sms_adapter()
        region = infer_sms_region_from_phone(patient.phone)
        adapter.send_sms(to=patient.phone, message=sms_text, default_region=region)

    return RequestOtpResult(
        status="ok",
        audit_outcome="sms_sent",
        patient_id=patient.id,
    )


def verify_otp(
    phone: str,
    date_of_birth: date,
    otp_code: str,
    last_name: str | None = None,
) -> VerifyOtpResult:
    """Verify OTP and return patient_id on success. Uses session for authenticated access."""
    patient = resolve_patient_for_portal(phone, date_of_birth, last_name)
    if not patient:
        return VerifyOtpResult(success=False, error="invalid")

    otp_stripped = (otp_code or "").strip()
    if len(otp_stripped) != 6 or not otp_stripped.isdigit():
        return VerifyOtpResult(success=False, error="invalid")

    now = timezone.now()
    session = (
        PatientResultsOtpSession.objects.select_related("patient")
        .filter(
            patient=patient,
            expires_at__gt=now,
            verified_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if not session:
        return VerifyOtpResult(success=False, error="invalid")

    if session.verify_attempt_count >= OTP_MAX_VERIFY_ATTEMPTS:
        return VerifyOtpResult(success=False, error="blocked")

    expected_hash = _hash_otp(otp_stripped)
    if session.otp_code_hash != expected_hash:
        session.verify_attempt_count += 1
        session.save(update_fields=["verify_attempt_count"])
        return VerifyOtpResult(success=False, error="invalid")

    # Atomic mark as verified
    updated = PatientResultsOtpSession.objects.filter(
        id=session.id,
        verified_at__isnull=True,
    ).update(verified_at=now)
    if updated == 0:
        return VerifyOtpResult(success=False, error="invalid")

    return VerifyOtpResult(
        success=True,
        patient_id=str(session.patient_id),
    )


def set_patient_results_session(request: "HttpRequest", patient_id: str) -> None:
    """Store patient_id in session for document access."""
    request.session["patient_results_patient_id"] = patient_id
    request.session["patient_results_verified_at"] = timezone.now().isoformat()


def get_patient_id_from_session(request: "HttpRequest") -> str | None:
    """Get patient_id from patient_results session."""
    return request.session.get("patient_results_patient_id")
