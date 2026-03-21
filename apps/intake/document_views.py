"""Read-only API views for intake document versions (PDF) for RECEPTION/ADMIN."""

from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.api_utils import json_error, require_auth, require_user_role
from apps.core.http_utils import get_client_ip
from apps.operations.services import create_audit_event
from apps.intake.models import IntakeDocumentVersion, IntakePdfStatus
from apps.intake.document_services import (
    check_intake_document_access,
    get_intake_document_detail,
    get_intake_document_list_item,
    list_intake_documents,
    parse_intake_documents_list_params,
    read_intake_pdf_bytes,
)


@require_auth
def intake_documents_view(request: HttpRequest) -> JsonResponse:
    """GET: list intake document versions (RECEPTION/ADMIN), scoped by clinic_site."""
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)

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
    meta = {
        "client_ip": get_client_ip(request),
        "page": params["page"],
        "page_size": params["page_size"],
        "total": total,
        "item_count": len(items),
    }
    if clinic_site_id:
        meta["clinic_site_id"] = str(clinic_site_id)
    create_audit_event(
        event_type="INTAKE_DOCUMENTS_LISTED",
        actor_user_id=request.user.id,
        context_clinic_site_id=clinic_site_id,
        metadata=meta,
    )
    return JsonResponse(
        {
            "items": [get_intake_document_list_item(v) for v in items],
            "pagination": {
                "page": params["page"],
                "page_size": params["page_size"],
                "total": total,
            },
        },
        status=200,
    )


@require_auth
def intake_document_detail_view(
    request: HttpRequest, intake_document_version_id: UUID
) -> JsonResponse:
    """GET: detail of one intake document version (RECEPTION/ADMIN)."""
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)

    try:
        version = (
            IntakeDocumentVersion.objects.select_related(
                "intake_form",
                "intake_form__queue_entry",
                "intake_form__queue_entry__patient",
                "intake_form__queue_entry__daily_queue",
                "intake_form__queue_entry__daily_queue__clinic_site",
            )
            .get(id=intake_document_version_id)
        )
    except ObjectDoesNotExist:
        return json_error("Intake document not found.", status=404)
    try:
        check_intake_document_access(version, request.user)
    except ObjectDoesNotExist:
        return json_error("Intake document not found.", status=404)
    qe = version.intake_form.queue_entry
    create_audit_event(
        event_type="INTAKE_DOCUMENT_VIEWED",
        actor_user_id=request.user.id,
        patient_id=qe.patient_id,
        context_clinic_site_id=qe.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            "intake_document_version_id": str(version.id),
        },
    )
    return JsonResponse(get_intake_document_detail(version), status=200)


@require_auth
def intake_document_preview_pdf_view(
    request: HttpRequest, intake_document_version_id: UUID
) -> HttpResponse | JsonResponse:
    """GET: serve PDF file inline (RECEPTION/ADMIN). 404 if not generated or file missing."""
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)

    try:
        version = (
            IntakeDocumentVersion.objects.select_related(
                "intake_form",
                "intake_form__queue_entry",
                "intake_form__queue_entry__daily_queue",
            )
            .get(id=intake_document_version_id)
        )
    except ObjectDoesNotExist:
        return json_error("Intake document not found.", status=404)
    try:
        check_intake_document_access(version, request.user)
    except ObjectDoesNotExist:
        return json_error("Intake document not found.", status=404)

    if version.pdf_generation_status != IntakePdfStatus.COMPLETED or not version.pdf_local_path:
        return json_error("PDF not yet generated or unavailable.", status=404)
    try:
        pdf_bytes = read_intake_pdf_bytes(version)
    except FileNotFoundError:
        return json_error("PDF file not found.", status=404)

    qe = version.intake_form.queue_entry
    create_audit_event(
        event_type="INTAKE_DOCUMENT_PDF_PREVIEWED",
        actor_user_id=request.user.id,
        patient_id=qe.patient_id,
        context_clinic_site_id=qe.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            "intake_document_version_id": str(version.id),
        },
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="intake-document.pdf"'
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response
