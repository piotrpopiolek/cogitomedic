from __future__ import annotations

from datetime import datetime
from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body, require_auth, require_user_role, safe_parse_positive_int
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding
from apps.medical.api_schemas import (
    CreateMedicalDocumentRequest,
    DoctorTemplateCreateRequest,
    DoctorTemplateListQuery,
    DoctorTemplateUpdateRequest,
    GenerateTextRequest,
    PublishMedicalDocumentRequest,
    SaveDraftMedicalDocumentRequest,
)
from apps.medical.befund_text import generate_befund_text
from apps.medical.models import MedicalDocument, MedicalDocumentVersion
from apps.medical.services import (
    create_or_get_medical_document,
    get_medical_document_context,
    list_medical_documents,
    publish_document_version,
    save_draft_document_version,
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


def _serialize_medical_document_list_item(doc) -> dict:
    """Serialize one medical document for list response; doc has prefetched versions (ordered -version_no)."""
    versions = list(doc.versions.all())
    latest = versions[0] if versions else None
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
    }


@require_auth
@csrf_exempt
def medical_documents_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method == "GET":
        status = request.GET.get("status") or None
        queue_date = None
        if request.GET.get("queue_date"):
            try:
                queue_date = datetime.strptime(request.GET.get("queue_date", ""), "%Y-%m-%d").date()
            except ValueError:
                pass
        patient_search = request.GET.get("patient_search") or None
        page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
        page_size = safe_parse_positive_int(request.GET.get("page_size"), default=20, maximum=200)
        items, total = list_medical_documents(
            status=status,
            queue_date=queue_date,
            patient_search=patient_search,
            page=page,
            page_size=page_size,
        )
        return JsonResponse(
            {
                "items": [_serialize_medical_document_list_item(d) for d in items],
                "pagination": {"page": page, "page_size": page_size, "total": total},
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
            document = create_or_get_medical_document(
                queue_entry_id=body.queue_entry_id,
                intake_form_id=body.intake_form_id,
                created_by_user_id=request.user.id,
            )
        except ObjectDoesNotExist:
            return json_error("Queue entry or intake form not found.", status=404)
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
@csrf_exempt
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
        )
    except ObjectDoesNotExist:
        return json_error("Medical document not found.", status=404)
    return JsonResponse(context, status=200)


@require_auth
@csrf_exempt
def medical_document_generate_text_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    """POST: generate Befund text from medical_payload (per lesion + summary). Does not save to DB."""
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = GenerateTextRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    if not MedicalDocument.objects.filter(id=medical_document_id).exists():
        return json_error("Medical document not found.", status=404)

    payload = body.medical_payload or {}
    if payload.get("schema_version") != body.medical_payload_schema_version:
        payload = {**payload, "schema_version": body.medical_payload_schema_version}
    result = generate_befund_text(payload, authoring_locale=body.authoring_locale)
    return JsonResponse(
        {
            "generated": True,
            "lesions": result["lesions"],
            "summary_generated_text": result["summary_generated_text"],
        },
        status=200,
    )


@require_auth
@csrf_exempt
def medical_document_versions_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    """GET: list versions of a medical document."""
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    try:
        MedicalDocument.objects.get(id=medical_document_id)
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
            "hidrive_sent": v["hidrive_sent"],
            "sms_sent": v["sms_sent"],
        }
        for v in versions
    ]
    return JsonResponse({"items": items}, status=200)


@require_auth
@csrf_exempt
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
        version = save_draft_document_version(
            medical_document_id=medical_document_id,
            updated_by_user_id=request.user.id,
            medical_payload_schema_version=body.medical_payload_schema_version,
            medical_payload=body.medical_payload.model_dump(),
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
@csrf_exempt
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
        version = publish_document_version(
            medical_document_id=medical_document_id,
            publish_request_id=body.publish_request_id,
            published_by_user_id=request.user.id,
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
        },
        status=200,
    )


@require_auth
@csrf_exempt
def medical_document_version_detail_view(request: HttpRequest, version_id: UUID) -> JsonResponse:
    """GET: single medical document version by id (MedicalDocumentVersion.id)."""
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    try:
        version = MedicalDocumentVersion.objects.select_related("medical_document").get(id=version_id)
    except ObjectDoesNotExist:
        return json_error("Medical document version not found.", status=404)
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
            "publish_request_id": str(version.publish_request_id) if version.publish_request_id else None,
            "created_at": version.created_at.isoformat(),
        },
        status=200,
    )


@require_auth
@csrf_exempt
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
                        "is_global": template.is_global,
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
                is_global=body.is_global,
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
                "is_global": template.is_global,
                "is_active": template.is_active,
            },
            status=201,
        )

    return json_error("Method not allowed.", status=405)


@require_auth
@csrf_exempt
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
                "is_global": template.is_global,
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
            "is_global": template.is_global,
            "is_active": template.is_active,
        },
        status=200,
    )
