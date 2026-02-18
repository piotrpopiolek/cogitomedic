from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body, require_auth, require_user_role
from apps.core.exceptions import DomainError
from apps.medical.api_schemas import (
    CreateMedicalDocumentRequest,
    DoctorTemplateCreateRequest,
    DoctorTemplateListQuery,
    DoctorTemplateUpdateRequest,
    PublishMedicalDocumentRequest,
    SaveDraftMedicalDocumentRequest,
)
from apps.medical.services import create_or_get_medical_document, publish_document_version, save_draft_document_version
from apps.medical.template_services import (
    TemplateListFilters,
    TemplateNotFoundError,
    create_template,
    list_templates,
    update_template,
)

@require_auth
@csrf_exempt
def medical_documents_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = CreateMedicalDocumentRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    if body.created_by_user_id != request.user.id:
        return json_error("Actor mismatch.", status=403)

    try:
        document = create_or_get_medical_document(
            queue_entry_id=body.queue_entry_id,
            intake_form_id=body.intake_form_id,
            created_by_user_id=body.created_by_user_id,
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
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    if body.updated_by_user_id != request.user.id:
        return json_error("Actor mismatch.", status=403)

    if body.medical_payload.get("schema_version") != body.medical_payload_schema_version:
        return json_error("medical_payload.schema_version must match medical_payload_schema_version.", status=400)

    try:
        version = save_draft_document_version(
            medical_document_id=medical_document_id,
            updated_by_user_id=body.updated_by_user_id,
            medical_payload_schema_version=body.medical_payload_schema_version,
            medical_payload=body.medical_payload,
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
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    if body.published_by_user_id != request.user.id:
        return json_error("Actor mismatch.", status=403)

    try:
        version = publish_document_version(
            medical_document_id=medical_document_id,
            publish_request_id=body.publish_request_id,
            published_by_user_id=body.published_by_user_id,
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
def doctor_text_templates_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"DOCTOR", "ADMIN"})
    if role_error:
        return role_error
    if request.method == "GET":
        try:
            query = DoctorTemplateListQuery.model_validate(
                {
                    "actor_user_id": request.GET.get("actor_user_id"),
                    "template_locale": request.GET.get("template_locale"),
                    "include_inactive": request.GET.get("include_inactive", "false").lower() == "true",
                }
            )
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        if query.actor_user_id != request.user.id:
            return json_error("Actor mismatch.", status=403)

        try:
            templates = list_templates(
                filters=TemplateListFilters(
                    actor_user_id=query.actor_user_id,
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
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        if body.actor_user_id != request.user.id:
            return json_error("Actor mismatch.", status=403)

        try:
            template = create_template(
                actor_user_id=body.actor_user_id,
                name=body.name,
                template_locale=body.template_locale,
                template_body=body.template_body,
                is_global=body.is_global,
                is_active=body.is_active,
            )
        except ObjectDoesNotExist:
            return json_error("Actor user not found.", status=404)
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
    if request.method != "PATCH":
        return json_error("Method not allowed.", status=405)

    try:
        body = DoctorTemplateUpdateRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    if body.actor_user_id != request.user.id:
        return json_error("Actor mismatch.", status=403)

    try:
        template = update_template(
            template_id=template_id,
            actor_user_id=body.actor_user_id,
            name=body.name,
            template_locale=body.template_locale,
            template_body=body.template_body,
            is_active=body.is_active,
        )
    except ObjectDoesNotExist:
        return json_error("Actor user not found.", status=404)
    except TemplateNotFoundError as exc:
        return json_error(str(exc), status=404)
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
