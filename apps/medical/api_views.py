from __future__ import annotations

import json
from uuid import UUID

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error
from apps.core.exceptions import DomainError
from apps.medical.api_schemas import (
    CreateMedicalDocumentRequest,
    PublishMedicalDocumentRequest,
    SaveDraftMedicalDocumentRequest,
)
from apps.medical.services import create_or_get_medical_document, publish_document_version, save_draft_document_version


def _read_json_body(request: HttpRequest) -> dict:
    return json.loads(request.body.decode("utf-8") or "{}")


@csrf_exempt
def medical_documents_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = CreateMedicalDocumentRequest.model_validate(_read_json_body(request))
    except json.JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    document = create_or_get_medical_document(
        queue_entry_id=body.queue_entry_id,
        intake_form_id=body.intake_form_id,
        created_by_user_id=body.created_by_user_id,
    )
    return JsonResponse(
        {
            "medical_document_id": str(document.id),
            "queue_entry_id": str(document.queue_entry_id),
            "status": document.status,
        },
        status=201,
    )


@csrf_exempt
def medical_document_draft_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    if request.method != "PUT":
        return json_error("Method not allowed.", status=405)
    try:
        body = SaveDraftMedicalDocumentRequest.model_validate(_read_json_body(request))
    except json.JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

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


@csrf_exempt
def medical_document_publish_view(request: HttpRequest, medical_document_id: UUID) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)
    try:
        body = PublishMedicalDocumentRequest.model_validate(_read_json_body(request))
    except json.JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        version = publish_document_version(
            medical_document_id=medical_document_id,
            publish_request_id=body.publish_request_id,
            published_by_user_id=body.published_by_user_id,
        )
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
