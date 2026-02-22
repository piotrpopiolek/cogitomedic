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

from apps.intake.models import IntakeStatus
from apps.medical.services import (
    create_or_get_medical_document,
    get_medical_document_context,
    list_doctor_work_queue,
)


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


@login_required(login_url="doctor-login")
@require_http_methods(["POST"])
@csrf_protect
def doctor_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("doctor-login")


def _doctor_role_ok(request: HttpRequest) -> bool:
    role = getattr(request.user, "role", None)
    return role in ("DOCTOR", "ADMIN")


@login_required(login_url="doctor-login")
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
    list_items, total = list_doctor_work_queue(
        status=status,
        queue_date=queue_date,
        patient_search=patient_search,
        page=page,
        page_size=page_size,
    )
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


@login_required(login_url="doctor-login")
@require_http_methods(["GET"])
def doctor_open_by_queue_view(request: HttpRequest, queue_entry_id: UUID) -> HttpResponse:
    """Create or get medical document for queue entry (with submitted intake) and redirect to detail."""
    if not _doctor_role_ok(request):
        return redirect("doctor-login")
    from apps.reception.models import QueueEntry

    try:
        entry = QueueEntry.objects.select_related("intake_form").get(id=queue_entry_id)
    except QueueEntry.DoesNotExist:
        return render(request, "doctor/error.html", {"message": "Eintrag nicht gefunden."}, status=404)
    if not getattr(entry, "intake_form", None):
        return render(request, "doctor/error.html", {"message": "Keine Ankiete für diesen Eintrag."}, status=404)
    intake_form = entry.intake_form
    if getattr(intake_form, "form_status", None) != IntakeStatus.SUBMITTED:
        return render(request, "doctor/error.html", {"message": "Ankiete noch nicht abgeschlossen."}, status=400)
    doc = create_or_get_medical_document(
        queue_entry_id=entry.id,
        intake_form_id=intake_form.id,
        created_by_user_id=request.user.id,
    )
    return redirect("doctor-document-detail", medical_document_id=doc.id)


@login_required(login_url="doctor-login")
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
