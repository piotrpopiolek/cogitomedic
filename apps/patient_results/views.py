"""HTML views for ergebnisse portal (patient results)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.shortcuts import redirect, render

from apps.core.translation_service import get_ergebnisse_ui_strings, normalize_language_code
from apps.patient_results.document_services import list_patient_documents
from apps.patient_results.services import (
    get_patient_id_from_session,
    request_otp,
    set_patient_results_session,
    verify_otp,
)


def _get_locale(request) -> str:
    """Get locale from ?locale= or Accept-Language, default de."""
    locale = request.GET.get("locale") or ""
    if not locale and hasattr(request, "META") and request.META.get("HTTP_ACCEPT_LANGUAGE"):
        # Parse first preferred language (e.g. "de-DE,de;q=0.9,en;q=0.8")
        accept = request.META["HTTP_ACCEPT_LANGUAGE"].split(",")[0].strip().split("-")[0]
        if accept in ("de", "en", "pl"):
            locale = accept
    return normalize_language_code(locale or "de")


def _ergebnisse_context(request, **extra):
    locale = _get_locale(request)
    ctx = {"ergebnisse_ui": get_ergebnisse_ui_strings(locale), "ergebnisse_locale": locale}
    ctx.update(extra)
    return ctx


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
    ui = _ergebnisse_context(request)
    ui["turnstile_site_key"] = getattr(settings, "TURNSTILE_SITE_KEY", "") or ""
    if request.method == "GET":
        return render(request, "ergebnisse/login.html", ui)
    phone = (request.POST.get("phone") or "").strip()
    dob_str = _parse_dob(request.POST.get("date_of_birth") or "")
    captcha_token = (request.POST.get("captcha_token") or "").strip()
    if not phone or not dob_str:
        ui["error"] = ui["ergebnisse_ui"].get("error_required", "Phone and date of birth are required.")
        return render(request, "ergebnisse/login.html", ui)
    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    result = request_otp(phone=phone, date_of_birth=dob, captcha_token=captcha_token)
    if result.status != "ok":
        ui["error"] = ui["ergebnisse_ui"].get("error_captcha", "CAPTCHA verification failed. Please try again.")
        return render(request, "ergebnisse/login.html", ui)
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
        return render(request, "ergebnisse/otp.html", _ergebnisse_context(request))
    phone = request.session.get("ergebnisse_phone")
    dob_str = request.session.get("ergebnisse_dob")
    if not phone or not dob_str:
        return redirect("ergebnisse:login")
    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    otp_code = (request.POST.get("otp_code") or "").strip()
    ui = _ergebnisse_context(request)
    if not otp_code:
        ui["error"] = ui["ergebnisse_ui"].get("error_otp_required", "Please enter the code.")
        return render(request, "ergebnisse/otp.html", ui)
    result = verify_otp(phone=phone, date_of_birth=dob, otp_code=otp_code)
    if not result.success:
        ui["error"] = ui["ergebnisse_ui"].get("error_invalid_otp", "Invalid or expired code. Please try again.")
        return render(request, "ergebnisse/otp.html", ui)
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
    return render(request, "ergebnisse/documents.html", _ergebnisse_context(request, items=items))
