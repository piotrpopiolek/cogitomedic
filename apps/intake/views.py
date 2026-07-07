"""Read-only admin panel views for intake document versions (PDF) for RECEPTION/ADMIN/MANAGER."""

from __future__ import annotations

from uuid import UUID

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.contrib import admin
from django.urls import reverse

from apps.core.admin_list_page_size import changelist_page_size_context
from apps.core.api_utils import get_scoped_clinic_site_ids
from apps.core.translation_service import get_admin_translation
from apps.core.staff_custom_admin import is_reception_admin_or_manager_staff
from apps.intake.document_services import (
    check_intake_document_access,
    get_intake_document_detail,
    get_intake_document_list_item,
    list_intake_documents,
    parse_intake_documents_list_params,
)
from apps.intake.models import IntakeDocumentVersion
from apps.reception.models import ClinicSite

_INTAKE_PDF_STATUS_ADMIN_KEYS: dict[str, tuple[str, str]] = {
    "PENDING": ("administration.pdf_status_pending", "Oczekuje"),
    "PROCESSING": ("administration.pdf_status_in_progress", "W trakcie"),
    "IN_PROGRESS": ("administration.pdf_status_in_progress", "W trakcie"),
    "COMPLETED": ("administration.pdf_status_completed", "Wygenerowany"),
    "FAILED": ("administration.pdf_status_failed", "Błąd"),
}


def _intake_pdf_status_display(request: HttpRequest, code: str | None) -> str:
    if not code:
        return ""
    key_default = _INTAKE_PDF_STATUS_ADMIN_KEYS.get(code)
    if key_default is None:
        return code
    key, default = key_default
    return get_admin_translation(request, key, default)


def _enrich_intake_document_list_items_for_display(
    request: HttpRequest,
    items: list[dict[str, object]],
) -> None:
    for item in items:
        code = item.get("pdf_generation_status")
        if isinstance(code, str) and code:
            item["pdf_generation_status_display"] = _intake_pdf_status_display(
                request, code
            )


@staff_member_required
def intake_documents_list_view(request: HttpRequest) -> HttpResponse:
    """List intake document versions; RECEPTION/ADMIN/MANAGER only, scoped by clinic_site."""
    if not is_reception_admin_or_manager_staff(request.user):
        return redirect("admin:index")

    params = parse_intake_documents_list_params(request.GET)
    clinic_site_id = None
    if params.get("clinic_site_id"):
        try:
            clinic_site_id = UUID(params["clinic_site_id"])
        except (ValueError, TypeError):
            pass

    items, total = list_intake_documents(
        user=request.user,
        queue_date=params.get("queue_date"),
        pdf_generation_status=params.get("pdf_generation_status"),
        patient_search=params.get("patient_search"),
        clinic_site_id=clinic_site_id,
        page=params["page"],
        page_size=params["page_size"],
    )
    list_data = [get_intake_document_list_item(v) for v in items]
    _enrich_intake_document_list_items_for_display(request, list_data)

    scope_ids = get_scoped_clinic_site_ids(request.user)
    clinic_sites = []
    if scope_ids is not None:
        qs = ClinicSite.objects.filter(id__in=scope_ids).order_by("name", "code")
    else:
        qs = ClinicSite.objects.all().order_by("name", "code")
    for site in qs.values("id", "name", "code"):
        clinic_sites.append(
            {"id": str(site["id"]), "name": site.get("name"), "code": site.get("code")}
        )

    page = params["page"]
    page_size = params["page_size"]
    get_copy = request.GET.copy()

    def pagination_url(p: int) -> str:
        q = get_copy.copy()
        q["page"] = p
        return "?" + q.urlencode()

    previous_page_url = pagination_url(page - 1) if page > 1 else None
    next_page_url = pagination_url(page + 1) if page * page_size < total else None

    context = {
        **admin.site.each_context(request),
        "title": get_admin_translation(
            request,
            "administration.intake_documents_list_title",
            "Dokumenty intake (PDF)",
        ),
        "items": list_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
        "previous_page_url": previous_page_url,
        "next_page_url": next_page_url,
        **changelist_page_size_context(request),
        "filters": {
            "queue_date": params.get("queue_date"),
            "pdf_generation_status": params.get("pdf_generation_status"),
            "patient_search": params.get("patient_search"),
            "clinic_site_id": params.get("clinic_site_id"),
        },
        "clinic_sites": clinic_sites,
    }
    return TemplateResponse(request, "admin/intake/documents_list.html", context)


@staff_member_required
def intake_document_detail_view(request: HttpRequest, version_id: UUID) -> HttpResponse:
    """Detail of one intake document version; RECEPTION/ADMIN/MANAGER only, scoped by clinic_site."""
    if not is_reception_admin_or_manager_staff(request.user):
        return redirect("admin:index")

    try:
        version = IntakeDocumentVersion.objects.select_related(
            "intake_form",
            "intake_form__queue_entry",
            "intake_form__queue_entry__patient",
            "intake_form__queue_entry__daily_queue",
            "intake_form__queue_entry__daily_queue__clinic_site",
        ).get(id=version_id)
    except IntakeDocumentVersion.DoesNotExist:
        context = {**admin.site.each_context(request), "not_found": True}
        return TemplateResponse(
            request, "admin/intake/document_detail.html", context, status=404
        )

    try:
        check_intake_document_access(version, request.user)
    except ObjectDoesNotExist:
        context = {**admin.site.each_context(request), "not_found": True}
        return TemplateResponse(
            request, "admin/intake/document_detail.html", context, status=404
        )

    detail = get_intake_document_detail(version)
    preview_pdf_url = reverse(
        "intake-document-preview-pdf",
        kwargs={"intake_document_version_id": version_id},
    )
    context = {
        **admin.site.each_context(request),
        "title": f"Dokument intake – {detail['patient']['last_name']} {detail['patient']['first_name']}",
        "doc": detail,
        "not_found": False,
        "preview_pdf_url": preview_pdf_url,
    }
    return TemplateResponse(request, "admin/intake/document_detail.html", context)
