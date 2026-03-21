from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse, JsonResponse
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body, require_auth, require_user_role, safe_parse_positive_int
from apps.core.http_utils import get_client_ip
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding
from apps.medical.api_schemas import (
    CreateMedicalDocumentRequest,
    DoctorTemplateCreateRequest,
    DoctorTemplateListQuery,
    DoctorTemplateUpdateRequest,
    PublishMedicalDocumentRequest,
    RetryProcessingRequest,
    SaveDraftMedicalDocumentRequest,
)
from apps.medical.pdf_builder import build_befund_pdf_bytes
from apps.medical.medical_payload_schemas import validate_medical_payload_v1
from apps.medical.models import MedicalDocument, MedicalDocumentVersion
from apps.reception.models import QueueEntry
from apps.medical.services import (
    _assigned_doctor_metadata,
    _event_status_to_stage_status,
    _latest_error_message,
    _latest_retryable_event,
    check_doctor_document_access,
    check_doctor_queue_entry_access,
    create_or_get_medical_document,
    get_medical_document_context,
    list_medical_documents,
    parse_medical_documents_list_params,
    publish_document_version,
    revoke_document_version,
    save_draft_document_version,
    retry_latest_document_processing,
)
from apps.medical.template_services import (
    TemplateListFilters,
    TemplateNotFoundError,
    TemplatePermissionError,
    create_template,
    get_template,
    list_templates,
    update_template,
)
from apps.operations.models import AuditEvent
from apps.operations.services import create_audit_event


def _serialize_medical_document_list_item(doc) -> dict:
    """Serialize one medical document for list response; doc has prefetched versions (ordered -version_no)."""
    versions = list(doc.versions.all())
    latest = versions[0] if versions else None
    events_by_type = {e.event_type: e for e in latest.outbox_events.all()} if latest else {}
    patient = doc.queue_entry.patient
    queue = doc.queue_entry.daily_queue
    return {
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
        "hidrive_status": _event_status_to_stage_status(
            events_by_type.get("HIDRIVE_UPLOAD"),
            completed=bool(latest and latest.hidrive_sent),
        )
        if latest
        else None,
        "sms_status": _event_status_to_stage_status(
            events_by_type.get("SMS_SEND"),
            completed=bool(latest and latest.sms_sent),
        )
        if latest
        else None,
        "processing_error_message": _latest_error_message(latest) if latest else None,
        "can_retry_processing": _latest_retryable_event(latest) is not None if latest else False,
    }


@require_auth
def medical_documents_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method == "GET":
        list_params = parse_medical_documents_list_params(request.GET)
        items, total = list_medical_documents(
            **list_params,
            user=request.user,
        )
        create_audit_event(
            event_type="MEDICAL_DOCUMENTS_LISTED",
            actor_user_id=request.user.id,
            metadata={
                "client_ip": get_client_ip(request),
                "page": list_params["page"],
                "page_size": list_params["page_size"],
                "total": total,
                "item_count": len(items),
            },
        )
        return JsonResponse(
            {
                "items": [_serialize_medical_document_list_item(d) for d in items],
                "pagination": {
                    "page": list_params["page"],
                    "page_size": list_params["page_size"],
                    "total": total,
                },
            },
            status=200,
        )
    if request.method == "POST":
        try:
            body = CreateMedicalDocumentRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except InvalidRequestBodyEncoding:
            return json_error("Invalid request encoding.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

        try:
            entry = QueueEntry.objects.select_related("daily_queue").get(id=body.queue_entry_id)
            check_doctor_queue_entry_access(entry, request.user)
            document = create_or_get_medical_document(
                queue_entry_id=body.queue_entry_id,
                intake_form_id=body.intake_form_id,
                created_by_user_id=request.user.id,
            )
        except ObjectDoesNotExist:
            return json_error("Queue entry or intake form not found.", status=404)
        except DomainError as exc:
            return json_error(str(exc), status=400)
        return JsonResponse(
            {
                "medical_document_id": str(document.id),
                "queue_entry_id": str(document.queue_entry_id),
                "status": document.status,
            },
            status=201,
        )
    return json_error("Method not allowed.", status=405)


@require_auth
def medical_document_detail_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    """GET full document context: intake summary + current version (for doctor panel)."""
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    form_locale = (request.GET.get("form_locale") or "de-DE")[:10]
    try:
        context = get_medical_document_context(
            medical_document_id=medical_document_id,
            form_locale=form_locale,
            user=request.user,
        )
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)
    doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_VIEWED",
        actor_user_id=request.user.id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            **_assigned_doctor_metadata(doc),
        },
    )
    return JsonResponse(context, status=200)


@require_auth
def medical_document_preview_pdf_view(request: HttpRequest, medical_document_id: UUID) -> HttpResponse:
    """GET: return PDF preview from the latest saved version (draft or published). Opens inline in browser."""
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)

    version = (
        MedicalDocumentVersion.objects.filter(medical_document_id=medical_document_id)
        .select_related("medical_document", "medical_document__queue_entry", "medical_document__queue_entry__patient")
        .order_by("-version_no")
        .first()
    )
    if not version:
        return json_error("No version to preview. Save a draft first.", status=404)

    form_locale = (request.GET.get("form_locale") or request.GET.get("authoring_locale") or "").strip()[:10]
    authoring_locale_override = form_locale if form_locale else None
    pdf_bytes = build_befund_pdf_bytes(version, authoring_locale_override=authoring_locale_override)
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_PDF_PREVIEWED",
        actor_user_id=request.user.id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            "version_no": version.version_no,
            **_assigned_doctor_metadata(doc),
        },
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="befund-preview.pdf"'
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@require_auth
def medical_document_versions_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    """GET: list versions of a medical document."""
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)

    versions = (
        MedicalDocumentVersion.objects.filter(medical_document_id=medical_document_id)
        .order_by("-version_no")
        .values(
            "id",
            "version_no",
            "version_status",
            "pdf_generation_status",
            "published_at",
            "revoked_at",
            "hidrive_sent",
            "sms_sent",
        )
    )
    items = [
        {
            "id": str(v["id"]),
            "version_no": v["version_no"],
            "version_status": v["version_status"],
            "pdf_generation_status": v["pdf_generation_status"],
            "published_at": v["published_at"].isoformat() if v["published_at"] else None,
            "revoked_at": v["revoked_at"].isoformat() if v["revoked_at"] else None,
            "hidrive_sent": v["hidrive_sent"],
            "sms_sent": v["sms_sent"],
        }
        for v in versions
    ]
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_VERSIONS_LISTED",
        actor_user_id=request.user.id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            "version_count": len(items),
            **_assigned_doctor_metadata(doc),
        },
    )
    return JsonResponse({"items": items}, status=200)


@require_auth
def medical_document_draft_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "PUT":
        return json_error("Method not allowed.", status=405)
    try:
        body = SaveDraftMedicalDocumentRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    if body.medical_payload.schema_version != body.medical_payload_schema_version:
        return json_error("medical_payload.schema_version must match medical_payload_schema_version.", status=400)

    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)

    payload_dict = body.medical_payload.model_dump()
    if body.medical_payload_schema_version == 1:
        try:
            payload_dict = validate_medical_payload_v1(payload_dict)
        except ValidationError as exc:
            details = [{"type": e.get("type"), "loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
            return JsonResponse({"error": "Invalid medical_payload (v1).", "details": details}, status=400)

    try:
        version = save_draft_document_version(
            medical_document_id=medical_document_id,
            updated_by_user_id=request.user.id,
            medical_payload_schema_version=body.medical_payload_schema_version,
            medical_payload=payload_dict,
            diagnosis_code=body.diagnosis_code,
            procedure_code=body.procedure_code,
        )
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)

    return JsonResponse(
        {
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            "version_status": version.version_status,
        },
        status=200,
    )


@require_auth
def medical_document_publish_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = PublishMedicalDocumentRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)

    try:
        version = publish_document_version(
            medical_document_id=medical_document_id,
            publish_request_id=body.publish_request_id,
            published_by_user_id=request.user.id,
            publish_locale=body.publish_locale,
            resend_sms=body.resend_sms,
        )
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)

    return JsonResponse(
        {
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            "version_status": version.version_status,
            "publish_request_id": str(version.publish_request_id) if version.publish_request_id else None,
            "publish_locale": version.publish_locale,
        },
        status=200,
    )


@require_auth
def medical_document_version_detail_view(request: HttpRequest, version_id: UUID) -> JsonResponse:
    """GET: single medical document version by id (MedicalDocumentVersion.id)."""
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    try:
        version = MedicalDocumentVersion.objects.select_related(
            "medical_document", "medical_document__queue_entry__daily_queue"
        ).get(id=version_id)
        check_doctor_document_access(version.medical_document, request.user)
    except ObjectDoesNotExist:
        return json_error("Medical document version not found.", status=404)
    mdoc = version.medical_document
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_VERSION_VIEWED",
        actor_user_id=request.user.id,
        patient_id=mdoc.queue_entry.patient_id,
        medical_document_id=mdoc.id,
        context_clinic_site_id=mdoc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "client_ip": get_client_ip(request),
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            **_assigned_doctor_metadata(mdoc),
        },
    )
    return JsonResponse(
        {
            "id": str(version.id),
            "medical_document_id": str(version.medical_document_id),
            "version_no": version.version_no,
            "version_status": version.version_status,
            "medical_payload_schema_version": version.medical_payload_schema_version,
            "medical_payload": version.medical_payload,
            "diagnosis_code": version.diagnosis_code,
            "procedure_code": version.procedure_code,
            "pdf_generation_status": version.pdf_generation_status,
            "hidrive_sent": version.hidrive_sent,
            "hidrive_sent_at": version.hidrive_sent_at.isoformat() if version.hidrive_sent_at else None,
            "sms_sent": version.sms_sent,
            "sms_sent_at": version.sms_sent_at.isoformat() if version.sms_sent_at else None,
            "published_at": version.published_at.isoformat() if version.published_at else None,
            "revoked_at": version.revoked_at.isoformat() if version.revoked_at else None,
            "publish_request_id": str(version.publish_request_id) if version.publish_request_id else None,
            "publish_locale": version.publish_locale,
            "created_at": version.created_at.isoformat(),
        },
        status=200,
    )


@require_auth
def medical_document_retry_processing_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN", "RECEPTION"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = RetryProcessingRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        body = RetryProcessingRequest()
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
        check_doctor_document_access(doc, request.user)
        retried = retry_latest_document_processing(
            medical_document_id=medical_document_id,
            actor=request.user,
            reason=body.reason,
        )
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=409)

    return JsonResponse(
        {
            "retried": True,
            "outbox_event_id": str(retried.id),
            "event_type": retried.event_type,
            "status": retried.status,
        },
        status=200,
    )


@require_auth
def medical_document_revoke_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    """POST: Revoke the current published version. Patient loses access in ergebnisse portal."""
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
        check_doctor_document_access(doc, request.user)
        version = revoke_document_version(
            medical_document_id=medical_document_id,
            revoked_by_user_id=request.user.id,
        )
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)
    return JsonResponse(
        {
            "medical_document_version_id": str(version.id),
            "version_no": version.version_no,
            "revoked_at": version.revoked_at.isoformat() if version.revoked_at else None,
        },
        status=200,
    )


@require_auth
def doctor_text_templates_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method == "GET":
        try:
            query = DoctorTemplateListQuery.model_validate(
                {
                    "template_locale": request.GET.get("template_locale"),
                    "include_inactive": request.GET.get("include_inactive", "false").lower() == "true",
                }
            )
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

        try:
            templates = list_templates(
                filters=TemplateListFilters(
                    actor_user_id=request.user.id,
                    template_locale=query.template_locale,
                    include_inactive=query.include_inactive,
                )
            )
        except ObjectDoesNotExist:
            return json_error("Actor user not found.", status=404)
        except DomainError as exc:
            return json_error(str(exc), status=400)

        return JsonResponse(
            {
                "results": [
                    {
                        "id": str(template.id),
                        "name": template.name,
                        "template_locale": template.template_locale,
                        "template_body": template.template_body,
                        "lesion_group_favorites": template.lesion_group_favorites or [],
                        "is_global": template.is_global,
                        "clinic_site_id": str(template.clinic_site_id) if template.clinic_site_id else None,
                        "is_active": template.is_active,
                        "owner_user_id": str(template.owner_user_id) if template.owner_user_id else None,
                    }
                    for template in templates
                ]
            },
            status=200,
        )

    if request.method == "POST":
        try:
            body = DoctorTemplateCreateRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except InvalidRequestBodyEncoding:
            return json_error("Invalid request encoding.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

        try:
            template = create_template(
                actor_user_id=request.user.id,
                name=body.name,
                template_locale=body.template_locale,
                template_body=body.template_body,
                lesion_group_favorites=[p.model_dump(mode="json") for p in body.lesion_group_favorites],
                is_global=body.is_global,
                clinic_site_id=body.clinic_site_id,
                is_active=body.is_active,
            )
        except ObjectDoesNotExist:
            return json_error("Actor user not found.", status=404)
        except TemplatePermissionError as exc:
            return json_error(str(exc), status=400)
        except DomainError as exc:
            return json_error(str(exc), status=400)

        return JsonResponse(
            {
                "id": str(template.id),
                "name": template.name,
                "template_locale": template.template_locale,
                "template_body": template.template_body,
                "lesion_group_favorites": template.lesion_group_favorites or [],
                "is_global": template.is_global,
                "clinic_site_id": str(template.clinic_site_id) if template.clinic_site_id else None,
                "is_active": template.is_active,
            },
            status=201,
        )

    return json_error("Method not allowed.", status=405)


@require_auth
def doctor_text_template_detail_view(request: HttpRequest, template_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method == "GET":
        try:
            template = get_template(template_id=template_id, actor_user_id=request.user.id)
        except TemplateNotFoundError:
            return json_error("Template not found.", status=404)
        return JsonResponse(
            {
                "id": str(template.id),
                "name": template.name,
                "template_locale": template.template_locale,
                "template_body": template.template_body,
                "lesion_group_favorites": template.lesion_group_favorites or [],
                "is_global": template.is_global,
                "clinic_site_id": str(template.clinic_site_id) if template.clinic_site_id else None,
                "is_active": template.is_active,
                "owner_user_id": str(template.owner_user_id) if template.owner_user_id else None,
            },
            status=200,
        )
    if request.method != "PATCH":
        return json_error("Method not allowed.", status=405)

    try:
        body = DoctorTemplateUpdateRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        template = update_template(
            template_id=template_id,
            actor_user_id=request.user.id,
            name=body.name,
            template_locale=body.template_locale,
            template_body=body.template_body,
            lesion_group_favorites=[p.model_dump(mode="json") for p in body.lesion_group_favorites]
            if body.lesion_group_favorites is not None
            else None,
            is_active=body.is_active,
        )
    except ObjectDoesNotExist:
        return json_error("Actor user not found.", status=404)
    except TemplateNotFoundError as exc:
        return json_error(str(exc), status=404)
    except TemplatePermissionError as exc:
        return json_error(str(exc), status=400)
    except DomainError as exc:
        return json_error(str(exc), status=400)

    return JsonResponse(
        {
            "id": str(template.id),
            "name": template.name,
            "template_locale": template.template_locale,
            "template_body": template.template_body,
            "lesion_group_favorites": template.lesion_group_favorites or [],
            "is_global": template.is_global,
            "is_active": template.is_active,
        },
        status=200,
    )


@require_auth
def medical_document_audit_trail_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    try:
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document_id)
        check_doctor_document_access(doc, request.user)
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)

    page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
    page_size = safe_parse_positive_int(request.GET.get("page_size"), default=20, maximum=200)
    qs = AuditEvent.objects.filter(medical_document_id=medical_document_id).order_by("-event_time")
    total = qs.count()
    start = (page - 1) * page_size
    events = list(qs[start : start + page_size])
    items = [
        {
            "id": str(event.id),
            "event_time": event.event_time.isoformat(),
            "event_type": event.event_type,
            "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
            "metadata": event.metadata,
        }
        for event in events
    ]
    return JsonResponse(
        {
            "items": items,
            "pagination": {"page": page, "page_size": page_size, "total": total},
        },
        status=200,
    )
