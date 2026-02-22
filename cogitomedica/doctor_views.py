"""
Doctor panel: list of medical documents and document detail with Befund form.
Requires authenticated user with role DOCTOR or ADMIN.
Staff login (HTML) shares Django session with API auth.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.medical.services import get_medical_document_context, list_medical_documents


@require_http_methods(["GET", "POST"])
@csrf_protect
def doctor_login_view(request: HttpRequest) -> HttpResponse:
    """Staff login (DOCTOR/ADMIN). Same session as API. Redirects to /doctor/ or next."""
    if request.user.is_authenticated and _doctor_role_ok(request):
        return redirect(request.GET.get("next") or "doctor-list")
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_active and _doctor_role_ok_request(user):
            login(request, user)
            return redirect(request.POST.get("next") or request.GET.get("next") or "doctor-list")
        return render(request, "doctor/login.html", {"error": "Ungültige Anmeldung oder keine Berechtigung."})
    return render(request, "doctor/login.html", {"next": request.GET.get("next") or ""})


def _doctor_role_ok_request(user) -> bool:
    role = getattr(user, "role", None)
    return role in ("DOCTOR", "ADMIN")


@login_required
@require_http_methods(["POST"])
@csrf_protect
def doctor_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("doctor-login")


def _doctor_role_ok(request: HttpRequest) -> bool:
    role = getattr(request.user, "role", None)
    return role in ("DOCTOR", "ADMIN")


@login_required
@require_http_methods(["GET"])
def doctor_list_view(request: HttpRequest) -> HttpResponse:
    """List medical documents (work queue) with optional filters."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    status = request.GET.get("status") or None
    queue_date = None
    if request.GET.get("queue_date"):
        try:
            queue_date = datetime.strptime(request.GET.get("queue_date", ""), "%Y-%m-%d").date()
        except ValueError:
            pass
    patient_search = request.GET.get("patient_search") or None
    page = max(1, min(10_000, int(request.GET.get("page") or 1)))
    page_size = max(1, min(200, int(request.GET.get("page_size") or 20)))
    items, total = list_medical_documents(
        status=status,
        queue_date=queue_date,
        patient_search=patient_search,
        page=page,
        page_size=page_size,
    )
    # Serialize for template (same shape as API list)
    list_items = []
    for doc in items:
        versions = list(doc.versions.all())
        latest = versions[0] if versions else None
        patient = doc.queue_entry.patient
        queue = doc.queue_entry.daily_queue
        list_items.append({
            "id": str(doc.id),
            "queue_entry_id": str(doc.queue_entry_id),
            "status": doc.status,
            "current_version_no": doc.current_version_no,
            "last_published_at": doc.last_published_at.isoformat() if doc.last_published_at else None,
            "queue_date": queue.queue_date.isoformat(),
            "patient": {
                "id": str(patient.id),
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "date_of_birth": patient.date_of_birth.isoformat(),
            },
            "pdf_generation_status": latest.pdf_generation_status if latest else None,
            "hidrive_sent": latest.hidrive_sent if latest else False,
            "sms_sent": latest.sms_sent if latest else False,
        })
    return render(
        request,
        "doctor/list.html",
        {
            "items": list_items,
            "pagination": {"page": page, "page_size": page_size, "total": total},
            "filters": {
                "status": status or "",
                "queue_date": request.GET.get("queue_date") or "",
                "patient_search": patient_search or "",
            },
        },
    )


@login_required
@require_http_methods(["GET"])
def doctor_document_detail_view(request: HttpRequest, medical_document_id: UUID) -> HttpResponse:
    """Document detail with intake summary and Befund form (data for client-side API calls)."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    try:
        context = get_medical_document_context(
            medical_document_id=medical_document_id,
            form_locale=request.GET.get("form_locale") or "de-DE",
        )
    except Exception:
        return render(request, "doctor/error.html", {"message": "Dokument nicht gefunden."}, status=404)
    fitzpatrick_choices = [
        ("TYPE_I", "Hauttyp I nach Fitzpatrick"),
        ("TYPE_II", "Hauttyp II nach Fitzpatrick"),
        ("TYPE_III", "Hauttyp III nach Fitzpatrick"),
        ("TYPE_IV", "Hauttyp IV nach Fitzpatrick"),
        ("TYPE_V", "Hauttyp V nach Fitzpatrick"),
        ("TYPE_VI", "Hauttyp VI nach Fitzpatrick"),
        ("TYPE_II_III", "Hauttyp II–III nach Fitzpatrick"),
        ("UNDETERMINED", "Hauttyp nicht eindeutig bestimmbar"),
    ]
    panel_data = {
        "documentId": str(medical_document_id),
        "apiBase": "/api/v1",
        "context": context,
    }
    return render(
        request,
        "doctor/detail.html",
        {
            "document_id": str(medical_document_id),
            "panel_data": panel_data,
            "api_base": "/api/v1",
            "fitzpatrick_choices": fitzpatrick_choices,
        },
    )
