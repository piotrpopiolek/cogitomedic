"""HTML views for ergebnisse portal (patient results)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.shortcuts import redirect, render

from apps.patient_results.document_services import list_patient_documents
from apps.patient_results.services import (
    get_patient_id_from_session,
    request_otp,
    set_patient_results_session,
    verify_otp,
)


def _parse_dob(value: str) -> str | None:
    """Parse date from DD.MM.YYYY or YYYY-MM-DD. Returns YYYY-MM-DD or None."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    try:
        if "-" in s:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        else:
            dt = datetime.strptime(s[:10], "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def ergebnisse_login_view(request):
    """GET: show login form. POST: request OTP, redirect to otp on success."""
    if request.method == "GET":
        return render(
            request,
            "ergebnisse/login.html",
            {"turnstile_site_key": getattr(settings, "TURNSTILE_SITE_KEY", "") or ""},
        )
    phone = (request.POST.get("phone") or "").strip()
    dob_str = _parse_dob(request.POST.get("date_of_birth") or "")
    captcha_token = (request.POST.get("captcha_token") or "").strip()
    if not phone or not dob_str:
        return render(
            request,
            "ergebnisse/login.html",
            {
                "error": "Telefonnummer und Geburtsdatum sind erforderlich.",
                "turnstile_site_key": getattr(settings, "TURNSTILE_SITE_KEY", "") or "",
            },
        )
    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    result = request_otp(phone=phone, date_of_birth=dob, captcha_token=captcha_token)
    if result.status != "ok":
        return render(
            request,
            "ergebnisse/login.html",
            {
                "error": "CAPTCHA konnte nicht bestätigt werden. Bitte versuchen Sie es erneut.",
                "turnstile_site_key": getattr(settings, "TURNSTILE_SITE_KEY", "") or "",
            },
        )
    request.session["ergebnisse_phone"] = phone
    request.session["ergebnisse_dob"] = dob_str
    return redirect("ergebnisse:otp")


def ergebnisse_otp_view(request):
    """GET: show OTP form (requires ergebnisse_phone/dob in session). POST: verify, redirect to documents."""
    if request.method == "GET":
        phone = request.session.get("ergebnisse_phone")
        dob = request.session.get("ergebnisse_dob")
        if not phone or not dob:
            return redirect("ergebnisse:login")
        return render(request, "ergebnisse/otp.html")
    phone = request.session.get("ergebnisse_phone")
    dob_str = request.session.get("ergebnisse_dob")
    if not phone or not dob_str:
        return redirect("ergebnisse:login")
    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    otp_code = (request.POST.get("otp_code") or "").strip()
    if not otp_code:
        return render(request, "ergebnisse/otp.html", {"error": "Bitte geben Sie den Code ein."})
    result = verify_otp(phone=phone, date_of_birth=dob, otp_code=otp_code)
    if not result.success:
        return render(
            request,
            "ergebnisse/otp.html",
            {"error": "Ungültiger oder abgelaufener Code. Bitte versuchen Sie es erneut."},
        )
    set_patient_results_session(request, result.patient_id or "")
    del request.session["ergebnisse_phone"]
    del request.session["ergebnisse_dob"]
    return redirect("ergebnisse:documents")


def ergebnisse_documents_view(request):
    """GET: list documents for logged-in patient. Requires patient_results session."""
    patient_id = get_patient_id_from_session(request)
    if not patient_id:
        return redirect("ergebnisse:login")
    items = list_patient_documents(UUID(patient_id))
    return render(request, "ergebnisse/documents.html", {"items": items})
