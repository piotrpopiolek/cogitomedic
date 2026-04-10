"""
Doctor panel: list of medical documents and document detail with Befund form.
Requires authenticated user with role DOCTOR or ADMIN.
Staff login (HTML) shares Django session with API auth.

Komunikaty błędów w szablonach są w trzech wersjach językowych (DE/EN/PL) zgodnie z lang;
przy dodawaniu nowych komunikatów uzupełnij wszystkie trzy warianty.
"""

from __future__ import annotations

from uuid import UUID

from django.contrib import admin
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.intake.models import IntakeStatus
from apps.medical.services import (
    acquire_document_lock,
    check_doctor_queue_entry_access,
    create_or_get_medical_document,
    get_medical_document_context,
    list_doctor_work_queue,
    parse_medical_documents_list_params,
)
from apps.reception.models import QueueEntry
from apps.core.translation_service import (
    get_doctor_ui,
    get_fitzpatrick_choices,
    get_translation_map,
    normalize_language_code,
)


def _render_doctor(
    request: HttpRequest,
    template_name: str,
    context: dict,
    *,
    status: int = 200,
) -> HttpResponse:
    """Render doctor templates with admin/unfold base context."""
    merged_context = {
        **admin.site.each_context(request),
        **context,
    }
    return render(request, template_name, merged_context, status=status)


def _safe_redirect_next(request: HttpRequest, default_view_name: str):
    """Return redirect URL from next param if safe (same host), else default view name."""
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if next_url and not url_has_allowed_host_and_scheme(next_url, request.get_host()):
        next_url = ""
    return redirect(next_url or default_view_name)


@require_http_methods(["GET", "POST"])
@csrf_protect
def doctor_login_view(request: HttpRequest) -> HttpResponse:
    """Staff login (DOCTOR/ADMIN). Same session as API. Redirects to /doctor/ or next."""
    if request.user.is_authenticated and _doctor_role_ok(request):
        next_url = (request.GET.get("next") or "").strip()
        if next_url and not url_has_allowed_host_and_scheme(
            next_url, request.get_host()
        ):
            next_url = ""
        return redirect(next_url or "doctor-list")
    lang = _get_doctor_lang(request)
    ui = get_doctor_ui(lang)
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active and _doctor_role_ok_request(user):
            login(request, user)
            if request.POST.get("lang") in ("de", "en", "pl") or request.GET.get(
                "lang"
            ) in ("de", "en", "pl"):
                request.session["doctor_lang"] = request.POST.get(
                    "lang"
                ) or request.GET.get("lang")
            return _safe_redirect_next(request, "doctor-list")
        return render(
            request,
            "doctor/login.html",
            {
                **admin.site.each_context(request),
                "error": "Ungültige Anmeldung oder keine Berechtigung.",
                "next": (request.POST.get("next") or "").strip(),
                "ui": ui,
                "lang": lang,
            },
        )
    next_val = (request.GET.get("next") or "").strip()
    if next_val and not url_has_allowed_host_and_scheme(next_val, request.get_host()):
        next_val = ""
    return render(
        request,
        "doctor/login.html",
        {**admin.site.each_context(request), "next": next_val, "ui": ui, "lang": lang},
    )


def _doctor_role_ok_request(user) -> bool:
    return user.is_authenticated and (user.is_doctor or user.is_admin_role)


@login_required(login_url="doctor-login")
@require_http_methods(["POST"])
@csrf_protect
def doctor_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("doctor-login")


def _doctor_role_ok(request: HttpRequest) -> bool:
    user = request.user
    return user.is_authenticated and (user.is_doctor or user.is_admin_role)


def _get_doctor_lang(request: HttpRequest) -> str:
    """Język panelu: z GET ?lang= lub sesji, domyślnie 'de'."""
    lang = request.GET.get("lang") or request.session.get("doctor_lang", "de")
    return "en" if lang == "en" else "pl" if lang == "pl" else "de"


def _apply_doctor_lang(request: HttpRequest) -> str:
    """Ustaw język z GET w sesji (jeśli podany) i zwróć aktualny lang."""
    lang = _get_doctor_lang(request)
    if request.GET.get("lang") in ("de", "en", "pl"):
        request.session["doctor_lang"] = request.GET.get("lang")
    return lang


@login_required(login_url="doctor-login")
@require_http_methods(["GET"])
def doctor_list_view(request: HttpRequest) -> HttpResponse:
    """List medical documents (work queue) with optional filters."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    list_params = parse_medical_documents_list_params(request.GET)
    list_items, total = list_doctor_work_queue(
        **list_params,
        user=request.user,
    )
    lang = _apply_doctor_lang(request)
    if request.GET.get("lang"):
        query = request.GET.copy()
        query.pop("lang", None)
        url = request.path + ("?" + query.urlencode() if query else "")
        return redirect(url or "doctor-list")
    return _render_doctor(
        request,
        "doctor/list.html",
        {
            "items": list_items,
            "pagination": {
                "page": list_params["page"],
                "page_size": list_params["page_size"],
                "total": total,
            },
            "filters": {
                "status": list_params["status"] or "",
                "queue_date": request.GET.get("queue_date") or "",
                "patient_search": list_params["patient_search"] or "",
            },
            "ui": get_doctor_ui(lang),
            "lang": lang,
        },
    )


@login_required(login_url="doctor-login")
@require_http_methods(["GET"])
def doctor_open_by_queue_view(
    request: HttpRequest, queue_entry_id: UUID
) -> HttpResponse:
    """Create or get medical document for queue entry (with submitted intake) and redirect to detail."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    lang = _get_doctor_lang(request)
    ui = get_doctor_ui(lang)
    try:
        entry = QueueEntry.objects.select_related("intake_form", "daily_queue").get(
            id=queue_entry_id
        )
        check_doctor_queue_entry_access(entry, request.user)
    except ObjectDoesNotExist:
        return _render_doctor(
            request,
            "doctor/error.html",
            {
                "message": (
                    "Eintrag nicht gefunden."
                    if lang == "de"
                    else "Entry not found." if lang == "en" else "Nie znaleziono wpisu."
                ),
                "ui": ui,
                "lang": lang,
            },
            status=404,
        )
    if not getattr(entry, "intake_form", None):
        return _render_doctor(
            request,
            "doctor/error.html",
            {
                "message": (
                    "Keine Ankiete für diesen Eintrag."
                    if lang == "de"
                    else (
                        "No questionnaire for this entry."
                        if lang == "en"
                        else "Brak ankiety dla tego wpisu."
                    )
                ),
                "ui": ui,
                "lang": lang,
            },
            status=404,
        )
    intake_form = entry.intake_form
    if getattr(intake_form, "form_status", None) != IntakeStatus.SUBMITTED:
        return _render_doctor(
            request,
            "doctor/error.html",
            {
                "message": (
                    "Ankiete noch nicht abgeschlossen."
                    if lang == "de"
                    else (
                        "Questionnaire not yet completed."
                        if lang == "en"
                        else "Ankieta nie została jeszcze zakończona."
                    )
                ),
                "ui": ui,
                "lang": lang,
            },
            status=400,
        )
    doc = create_or_get_medical_document(
        queue_entry_id=entry.id,
        intake_form_id=intake_form.id,
        created_by_user_id=request.user.id,
    )
    url = reverse("doctor-document-detail", kwargs={"medical_document_id": doc.id})
    return HttpResponseRedirect(url + "?lang=" + lang)


@login_required(login_url="doctor-login")
@require_http_methods(["GET"])
def doctor_document_detail_view(
    request: HttpRequest, medical_document_id: UUID
) -> HttpResponse:
    """Document detail with intake summary and Befund form (data for client-side API calls)."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    lang = _get_doctor_lang(request)
    ui = get_doctor_ui(lang)
    try:
        context = get_medical_document_context(
            medical_document_id=medical_document_id,
            form_locale=request.GET.get("form_locale")
            or ("en-GB" if lang == "en" else "pl-PL" if lang == "pl" else "de-DE"),
            user=request.user,
        )
    except ObjectDoesNotExist:
        return _render_doctor(
            request,
            "doctor/error.html",
            {
                "message": (
                    "Dokument nicht gefunden."
                    if lang == "de"
                    else (
                        "Document not found."
                        if lang == "en"
                        else "Nie znaleziono dokumentu."
                    )
                ),
                "ui": ui,
                "lang": lang,
            },
            status=404,
        )
    granted, lock_holder = acquire_document_lock(
        medical_document_id=medical_document_id, user=request.user
    )
    if not granted:
        loc = normalize_language_code(lang)
        mapping = get_translation_map("doctor", loc)
        tmpl = mapping.get(
            "doctor.document_locked_error",
            (
                "Dieses Dokument wird gerade von {username} bearbeitet. "
                "Bitte versuchen Sie es später erneut."
            ),
        )
        message = tmpl.format(username=lock_holder or "…")
        return _render_doctor(
            request,
            "doctor/error.html",
            {"message": message, "ui": ui, "lang": lang},
            status=423,
        )
    fitzpatrick_choices = get_fitzpatrick_choices(lang)
    authoring_locale = "en-GB" if lang == "en" else "pl-PL" if lang == "pl" else "de-DE"
    if "authoring_locale" not in context:
        context["authoring_locale"] = authoring_locale
    panel_data = {
        "documentId": str(medical_document_id),
        "apiBase": "/api/v1",
        "context": context,
        "ui": get_doctor_ui(lang),
        "listUrl": request.build_absolute_uri(reverse("doctor-list")),
    }
    return _render_doctor(
        request,
        "doctor/detail.html",
        {
            "document_id": str(medical_document_id),
            "panel_data": panel_data,
            "api_base": "/api/v1",
            "fitzpatrick_choices": fitzpatrick_choices,
            "ui": ui,
            "lang": lang,
        },
    )
