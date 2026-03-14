"""Portal wyniki – OTP request/verify services."""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integrations.sms.client import get_sms_adapter
from apps.reception.models import Patient

if TYPE_CHECKING:
    from django.http import HttpRequest

OTP_VALID_MINUTES = 15
OTP_MAX_VERIFY_ATTEMPTS = 5
OTP_RATE_LIMIT_PER_HOUR = 3

# Simple OTP SMS template (DE default) – no DB translation for Phase 2 to avoid migration dependency
_DEFAULT_OTP_SMS = "CogitoMed: Ihr Code lautet {otp}"


def normalize_phone(value: str) -> str:
    """Normalize phone for lookup; digits only, matches import format."""
    digits = re.sub(r"[^\d]", "", value)
    return digits if digits else ""


def _phone_match_q(phone_normalized: str):
    """Q filter to match Patient.phone (stored as digits or +digits)."""
    from django.db.models import Q

    if not phone_normalized:
        return Q(pk=None)  # no match
    return Q(phone=phone_normalized) | Q(phone=f"+{phone_normalized}")


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
        import requests

        resp = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": token},
            timeout=10,
        )
        data = resp.json()
        return bool(data.get("success"))
    except Exception:
        return False


def _get_otp_sms_text(otp_code: str, locale: str | None = None) -> str:
    """Return SMS text for OTP code (simple template for Phase 2)."""
    return _DEFAULT_OTP_SMS.format(otp=otp_code)


@dataclass(frozen=True)
class RequestOtpResult:
    """Result of request_otp. status='ok' when accepted; error set when CAPTCHA fails."""

    status: str  # "ok" | "captcha_failed"
    error: str | None = None  # "captcha_failed" when CAPTCHA invalid


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
) -> RequestOtpResult:
    """
    Request OTP for patient results. Sends SMS if patient exists.
    Always returns success-like response to prevent enumeration.
    """
    if not _verify_captcha(captcha_token):
        return RequestOtpResult(status="captcha_failed", error="captcha_failed")

    phone_norm = normalize_phone(phone)
    if len(phone_norm) < 7:
        return RequestOtpResult(status="ok")


    # Rate limit: max 3 OTP per number per hour
    since = timezone.now() - timedelta(hours=1)
    from apps.patient_results.models import PatientResultsOtpSession

    recent_count = PatientResultsOtpSession.objects.filter(
        phone=phone_norm,
        created_at__gte=since,
    ).count()
    if recent_count >= OTP_RATE_LIMIT_PER_HOUR:
        return RequestOtpResult(status="ok")  # Don't reveal rate limit

    patient = (
        Patient.objects.filter(
            _phone_match_q(phone_norm),
            date_of_birth=date_of_birth,
        )
        .order_by("created_at")
        .first()
    )
    if not patient:
        return RequestOtpResult(status="ok")  # Don't reveal patient existence

    otp_code = f"{random.randint(100000, 999999)}"
    otp_hash = _hash_otp(otp_code)
    expires_at = timezone.now() + timedelta(minutes=OTP_VALID_MINUTES)

    try:
        with transaction.atomic():
            session = PatientResultsOtpSession.objects.create(
                patient=patient,
                phone=phone_norm,
                otp_code_hash=otp_hash,
                expires_at=expires_at,
            )
            sms_text = _get_otp_sms_text(otp_code)
            adapter = get_sms_adapter()
            adapter.send_sms(to=patient.phone, message=sms_text)
    except Exception:
        # Rollback via transaction
        raise

    return RequestOtpResult(status="ok")  # OTP sent


def verify_otp(
    phone: str,
    date_of_birth: date,
    otp_code: str,
) -> VerifyOtpResult:
    """Verify OTP and return patient_id on success. Uses session for authenticated access."""
    phone_norm = normalize_phone(phone)
    if len(phone_norm) < 7:
        return VerifyOtpResult(success=False, error="invalid")

    otp_stripped = (otp_code or "").strip()
    if len(otp_stripped) != 6 or not otp_stripped.isdigit():
        return VerifyOtpResult(success=False, error="invalid")

    from apps.patient_results.models import PatientResultsOtpSession

    now = timezone.now()
    session = (
        PatientResultsOtpSession.objects.select_related("patient")
        .filter(
            phone=phone_norm,
            patient__date_of_birth=date_of_birth,
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
