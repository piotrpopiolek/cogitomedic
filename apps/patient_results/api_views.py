"""API views for patient results portal (public + session-based)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from apps.core.api_utils import json_error, read_json_body
from apps.core.http_utils import get_client_ip
from apps.operations.services import create_audit_event
from apps.patient_results.document_services import (
    get_patient_pdf_path,
    list_patient_documents,
    resolve_patient_befund_download,
)
from apps.patient_results.services import (
    get_patient_id_from_session,
    request_otp,
    set_patient_results_session,
    verify_otp,
)


def _parse_date(s: str | None) -> date | None:
    """Parse YYYY-MM-DD. Returns None on invalid or out-of-range (future, >120 years ago)."""
    if not s or not isinstance(s, str):
        return None
    try:
        d = datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    today = timezone.now().date()
    if d > today:
        return None
    if d < today - timedelta(days=120 * 365):
        return None
    return d


@ratelimit(key="ip", rate="10/m", method="POST", block=True)
def patient_results_request_otp_view(request: HttpRequest) -> JsonResponse:
    """POST: Request OTP for patient results. Public, no auth. CAPTCHA required."""
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        body = read_json_body(request)
    except Exception:
        return json_error("other.api.invalid_json_body", status=400)
    phone = (body.get("phone") or "").strip()
    dob_str = body.get("date_of_birth")
    captcha_token = (body.get("captcha_token") or "").strip()
    if not phone:
        return json_error("other.api.phone_required", status=400)
    if not dob_str:
        return json_error("other.api.date_of_birth_required", status=400)
    dob = _parse_date(str(dob_str))
    if not dob:
        return json_error("other.api.date_of_birth_format", status=400)
    result = request_otp(phone=phone, date_of_birth=dob, captcha_token=captcha_token)
    client_ip = get_client_ip(request)
    meta = {"client_ip": client_ip, "outcome": result.audit_outcome}
    create_audit_event(
        event_type="PATIENT_RESULTS_OTP_REQUEST",
        patient_id=result.patient_id,
        metadata=meta,
    )
    if result.status == "captcha_failed":
        return json_error("other.api.captcha_verification_failed", status=400)
    return JsonResponse({"status": "ok"}, status=200)


@ratelimit(key="ip", rate="15/m", method="POST", block=True)
def patient_results_verify_otp_view(request: HttpRequest) -> JsonResponse:
    """POST: Verify OTP and establish patient results session. Public, no auth."""
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)
    try:
        body = read_json_body(request)
    except Exception:
        return json_error("other.api.invalid_json_body", status=400)
    phone = (body.get("phone") or "").strip()
    dob_str = body.get("date_of_birth")
    otp_code = (body.get("otp_code") or "").strip()
    if not phone:
        return json_error("other.api.phone_required", status=400)
    if not dob_str:
        return json_error("other.api.date_of_birth_required", status=400)
    dob = _parse_date(str(dob_str))
    if not dob:
        return json_error("other.api.date_of_birth_format", status=400)
    if not otp_code:
        return json_error("other.api.otp_code_required", status=400)
    result = verify_otp(phone=phone, date_of_birth=dob, otp_code=otp_code)
    client_ip = get_client_ip(request)
    if not result.success:
        outcome = result.error or "invalid"
        create_audit_event(
            event_type="PATIENT_RESULTS_OTP_VERIFY",
            metadata={"client_ip": client_ip, "outcome": outcome},
        )
        return json_error("other.api.invalid_or_expired_code", status=400)
    patient_uuid = UUID(result.patient_id or "")
    create_audit_event(
        event_type="PATIENT_RESULTS_OTP_VERIFY",
        patient_id=patient_uuid,
        metadata={"client_ip": client_ip, "outcome": "success"},
    )
    set_patient_results_session(request, result.patient_id or "")
    return JsonResponse({"status": "ok"}, status=200)


def _require_patient_session(request: HttpRequest) -> JsonResponse | str:
    """Return 401 JsonResponse if no patient_results session, else patient_id."""
    patient_id = get_patient_id_from_session(request)
    if not patient_id:
        return json_error("other.api.session_otp_required", status=401)
    return patient_id


def patient_results_documents_view(request: HttpRequest) -> JsonResponse:
    """GET: List documents for logged-in patient. Requires patient_results session."""
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    check = _require_patient_session(request)
    if isinstance(check, JsonResponse):
        return check
    patient_id = UUID(check)
    items = list_patient_documents(patient_id)
    create_audit_event(
        event_type="PATIENT_RESULTS_DOCUMENTS_LISTED",
        patient_id=patient_id,
        metadata={"client_ip": get_client_ip(request), "item_count": len(items)},
    )
    return JsonResponse({"items": items}, status=200)


def patient_results_download_view(
    request: HttpRequest, version_id: UUID
) -> HttpResponse | JsonResponse:
    """GET: Download PDF for version. Requires patient_results session."""
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)
    check = _require_patient_session(request)
    if isinstance(check, JsonResponse):
        return check
    patient_id = UUID(check)
    resolution, version = resolve_patient_befund_download(version_id, patient_id)
    if resolution == "not_found":
        create_audit_event(
            event_type="PATIENT_RESULTS_PDF_DOWNLOAD_DENIED",
            patient_id=patient_id,
            metadata={
                "client_ip": get_client_ip(request),
                "version_id": str(version_id),
                "reason": "version_not_found",
            },
        )
        return json_error("other.api.document_not_found", status=404)
    if resolution == "retention_expired":
        create_audit_event(
            event_type="PATIENT_RESULTS_PDF_DOWNLOAD_DENIED",
            patient_id=patient_id,
            medical_document_id=version.medical_document_id if version else None,
            metadata={
                "client_ip": get_client_ip(request),
                "version_id": str(version_id),
                "reason": "retention_expired",
            },
        )
        return json_error("other.api.document_retention_expired", status=410)
    assert version is not None
    path = get_patient_pdf_path(version_id, patient_id, version=version)
    if not path:
        create_audit_event(
            event_type="PATIENT_RESULTS_PDF_DOWNLOAD_DENIED",
            patient_id=patient_id,
            medical_document_id=version.medical_document_id,
            metadata={
                "client_ip": get_client_ip(request),
                "version_id": str(version_id),
                "reason": "file_missing",
            },
        )
        return json_error("other.api.document_not_found", status=404)
    queue_date = version.medical_document.queue_entry.daily_queue.queue_date.isoformat()
    filename = f"befund-{queue_date}.pdf"
    with open(path, "rb") as f:
        content = f.read()
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store, max-age=0"
    create_audit_event(
        event_type="PATIENT_RESULTS_PDF_DOWNLOAD",
        patient_id=patient_id,
        medical_document_id=version.medical_document_id,
        metadata={
            "version_id": str(version_id),
            "client_ip": get_client_ip(request),
        },
    )
    return response
