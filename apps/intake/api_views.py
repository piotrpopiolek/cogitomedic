from __future__ import annotations

import json
from uuid import UUID

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error
from apps.core.exceptions import DomainError, StateTransitionError
from apps.intake.api_schemas import SubmitIntakeFormRequest, UpdateAnamnesisPayloadRequest
from apps.intake.services import save_intake_anamnesis_payload, submit_patient_intake_form


@csrf_exempt
def intake_form_anamnesis_view(request: HttpRequest, intake_form_id: UUID) -> JsonResponse:
    if request.method != "PUT":
        return json_error("Method not allowed.", status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        body = UpdateAnamnesisPayloadRequest.model_validate(payload)
    except json.JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        intake_form = save_intake_anamnesis_payload(
            intake_form_id=intake_form_id,
            anamnesis_schema_version=body.anamnesis_schema_version,
            answers_payload=[answer.model_dump() for answer in body.answers],
        )
    except StateTransitionError as exc:
        return json_error(str(exc), status=409)

    return JsonResponse(
        {
            "intake_form_id": str(intake_form.id),
            "anamnesis_schema_version": intake_form.anamnesis_schema_version,
            "answer_count": len(intake_form.anamnesis_payload.get("answers", [])),
        },
        status=200,
    )


@csrf_exempt
def intake_form_submit_view(request: HttpRequest, intake_form_id: UUID) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        body = SubmitIntakeFormRequest.model_validate(payload)
    except json.JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        intake_form = submit_patient_intake_form(
            intake_form_id=intake_form_id,
            submitted_by_user_id=body.submitted_by_user_id,
        )
    except DomainError as exc:
        return json_error(str(exc), status=400)

    return JsonResponse(
        {
            "intake_form_id": str(intake_form.id),
            "form_status": intake_form.form_status,
            "submitted_at": intake_form.submitted_at.isoformat() if intake_form.submitted_at else None,
        },
        status=200,
    )
