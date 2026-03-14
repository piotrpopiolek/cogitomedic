"""API views for patient results portal (public + session-based)."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.api_utils import json_error, read_json_body
from apps.operations.services import create_audit_event
from apps.patient_results.document_services import (
    get_patient_pdf_path,
    get_patient_pdf_version,
    list_patient_documents,
)
from apps.patient_results.services import (
    get_patient_id_from_session,
    request_otp,
    set_patient_results_session,
    verify_otp,
)


def _parse_date(s: str | None) -> date | None:
    """Parse YYYY-MM-DD. Returns None on invalid."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def patient_results_request_otp_view(request: HttpRequest) -> JsonResponse:
    """POST: Request OTP for patient results. Public, no auth. CAPTCHA required."""
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = read_json_body(request)
    except Exception:
        return json_error("Invalid JSON body.", status=400)
    phone = (body.get("phone") or "").strip()
    dob_str = body.get("date_of_birth")
    captcha_token = (body.get("captcha_token") or "").strip()
    if not phone:
        return json_error("phone is required.", status=400)
    if not dob_str:
        return json_error("date_of_birth is required.", status=400)
    dob = _parse_date(str(dob_str))
    if not dob:
        return json_error("date_of_birth must be YYYY-MM-DD.", status=400)
    result = request_otp(phone=phone, date_of_birth=dob, captcha_token=captcha_token)
    if result.status == "captcha_failed":
        return json_error("CAPTCHA verification failed.", status=400)
    return JsonResponse({"status": "ok"}, status=200)


def patient_results_verify_otp_view(request: HttpRequest) -> JsonResponse:
    """POST: Verify OTP and establish patient results session. Public, no auth."""
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = read_json_body(request)
    except Exception:
        return json_error("Invalid JSON body.", status=400)
    phone = (body.get("phone") or "").strip()
    dob_str = body.get("date_of_birth")
    otp_code = (body.get("otp_code") or "").strip()
    if not phone:
        return json_error("phone is required.", status=400)
    if not dob_str:
        return json_error("date_of_birth is required.", status=400)
    dob = _parse_date(str(dob_str))
    if not dob:
        return json_error("date_of_birth must be YYYY-MM-DD.", status=400)
    if not otp_code:
        return json_error("otp_code is required.", status=400)
    result = verify_otp(phone=phone, date_of_birth=dob, otp_code=otp_code)
    if not result.success:
        return json_error("Invalid or expired code.", status=400)
    set_patient_results_session(request, result.patient_id or "")
    return JsonResponse({"status": "ok"}, status=200)


def _require_patient_session(request: HttpRequest) -> JsonResponse | str:
    """Return 401 JsonResponse if no patient_results session, else patient_id."""
    patient_id = get_patient_id_from_session(request)
    if not patient_id:
        return json_error("Session required. Please verify OTP first.", status=401)
    return patient_id


def patient_results_documents_view(request: HttpRequest) -> JsonResponse:
    """GET: List documents for logged-in patient. Requires patient_results session."""
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    check = _require_patient_session(request)
    if isinstance(check, JsonResponse):
        return check
    patient_id = UUID(check)
    items = list_patient_documents(patient_id)
    return JsonResponse({"items": items}, status=200)


def patient_results_download_view(request: HttpRequest, version_id: UUID) -> HttpResponse | JsonResponse:
    """GET: Download PDF for version. Requires patient_results session."""
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    check = _require_patient_session(request)
    if isinstance(check, JsonResponse):
        return check
    patient_id = UUID(check)
    version = get_patient_pdf_version(version_id, patient_id)
    if not version:
        return json_error("Document not found or unavailable.", status=404)
    path = get_patient_pdf_path(version_id, patient_id)
    if not path:
        return json_error("Document not found or unavailable.", status=404)
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
        metadata={"version_id": str(version_id)},
    )
    return response
