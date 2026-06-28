"""Audit events for patient results portal HTML views (ergebnisse/*)."""

from __future__ import annotations

from uuid import UUID

from django.http import HttpRequest

from apps.core.http_utils import get_client_ip
from apps.operations.services import create_audit_event
from apps.patient_results.services import RequestOtpResult, VerifyOtpResult

_HTML_CHANNEL = "html"


def audit_patient_results_otp_request(
    request: HttpRequest, result: RequestOtpResult
) -> None:
    create_audit_event(
        event_type="PATIENT_RESULTS_OTP_REQUEST",
        patient_id=result.patient_id,
        metadata={
            "client_ip": get_client_ip(request),
            "outcome": result.audit_outcome,
            "channel": _HTML_CHANNEL,
        },
    )


def audit_patient_results_otp_verify(
    request: HttpRequest, result: VerifyOtpResult
) -> None:
    client_ip = get_client_ip(request)
    if not result.success:
        create_audit_event(
            event_type="PATIENT_RESULTS_OTP_VERIFY",
            metadata={
                "client_ip": client_ip,
                "outcome": result.error or "invalid",
                "channel": _HTML_CHANNEL,
            },
        )
        return
    patient_uuid = UUID(result.patient_id) if result.patient_id else None
    create_audit_event(
        event_type="PATIENT_RESULTS_OTP_VERIFY",
        patient_id=patient_uuid,
        metadata={
            "client_ip": client_ip,
            "outcome": "success",
            "channel": _HTML_CHANNEL,
        },
    )


def audit_patient_results_documents_listed(
    request: HttpRequest, *, patient_id: UUID, item_count: int
) -> None:
    create_audit_event(
        event_type="PATIENT_RESULTS_DOCUMENTS_LISTED",
        patient_id=patient_id,
        metadata={
            "client_ip": get_client_ip(request),
            "item_count": item_count,
            "channel": _HTML_CHANNEL,
        },
    )
