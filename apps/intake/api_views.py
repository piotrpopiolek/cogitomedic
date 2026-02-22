from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body, require_auth, require_user_role
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding, StateTransitionError
from apps.intake.api_schemas import (
    SignatureUploadRequest,
    SubmitIntakeFormRequest,
    UpdateAnamnesisPayloadRequest,
    UpdateBodyMapRequest,
    UpdateConsentsRequest,
)
from apps.intake.services import (
    ConsentNotActiveError,
    InvalidSignatureError,
    get_intake_form_context,
    save_intake_anamnesis_payload,
    save_intake_body_map,
    save_intake_consents,
    save_intake_signature,
    submit_patient_intake_form,
)


def _intake_form_context_json(intake_form_id: UUID, request: HttpRequest) -> JsonResponse:
    """Build and return GET intake form context (shared by view and PATCH response)."""
    is_tablet = getattr(request.user, "role", None) == "TABLET"
    form_locale = request.GET.get("form_locale", "de-DE")[:10]
    context = get_intake_form_context(
        intake_form_id=intake_form_id,
        form_locale=form_locale,
        tablet_restrict_to_today=is_tablet,
    )
    return JsonResponse(context)


@require_auth
def intake_form_detail_view(request: HttpRequest, intake_form_id: UUID) -> JsonResponse:
    """GET intake form context; PATCH body_map_data."""
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "TABLET"})
    if role_error:
        return role_error
    if request.method == "GET":
        try:
            return _intake_form_context_json(intake_form_id, request)
        except ObjectDoesNotExist:
            return json_error("Intake form not found.", status=404)
    if request.method == "PATCH":
        try:
            body = UpdateBodyMapRequest.model_validate(read_json_body(request))
        except JSONDecodeError:
            return json_error("Invalid JSON payload.", status=400)
        except InvalidRequestBodyEncoding:
            return json_error("Invalid request encoding.", status=400)
        except ValidationError as exc:
            return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
        try:
            body_map_data = [p.model_dump() for p in body.body_map_data]
            intake_form = save_intake_body_map(
                intake_form_id=intake_form_id,
                body_map_schema_version=body.body_map_schema_version,
                body_map_data=body_map_data,
            )
        except ObjectDoesNotExist:
            return json_error("Intake form not found.", status=404)
        except StateTransitionError as exc:
            return json_error(str(exc), status=409)
        return JsonResponse({
            "intake_form_id": str(intake_form.id),
            "body_map_schema_version": intake_form.body_map_schema_version,
            "body_map_data": intake_form.body_map_data,
        })
    return json_error("Method not allowed.", status=405)


@require_auth
@require_http_methods(["PUT"])
def intake_form_consents_view(request: HttpRequest, intake_form_id: UUID) -> JsonResponse:
    """PUT intake form consents (acceptance set)."""
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "TABLET"})
    if role_error:
        return role_error
    try:
        body = UpdateConsentsRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        intake_form = save_intake_consents(
            intake_form_id=intake_form_id,
            consents_payload=[c.model_dump() for c in body.consents],
        )
    except ObjectDoesNotExist:
        return json_error("Intake form not found.", status=404)
    except StateTransitionError as exc:
        return json_error(str(exc), status=409)
    except ConsentNotActiveError as exc:
        return json_error(str(exc), status=409)
    # Return updated consents (accepted + accepted_at for accepted ones)
    from apps.intake.models import PatientIntakeConsent

    updated = list(
        PatientIntakeConsent.objects.filter(intake_form_id=intake_form.id).values(
            "consent_definition_id", "accepted", "accepted_at"
        )
    )
    consents_response = [
        {
            "consent_definition_id": str(u["consent_definition_id"]),
            "accepted": u["accepted"],
            "accepted_at": u["accepted_at"].isoformat() if u["accepted_at"] else None,
        }
        for u in updated
    ]
    return JsonResponse({"intake_form_id": str(intake_form.id), "consents": consents_response})


@require_auth
@require_http_methods(["POST"])
def intake_form_signature_view(request: HttpRequest, intake_form_id: UUID) -> JsonResponse:
    """POST upload signature (base64 image)."""
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "TABLET"})
    if role_error:
        return role_error
    try:
        body = SignatureUploadRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)
    try:
        intake_form = save_intake_signature(
            intake_form_id=intake_form_id,
            signature_base64=body.signature_base64,
        )
    except ObjectDoesNotExist:
        return json_error("Intake form not found.", status=404)
    except StateTransitionError as exc:
        return json_error(str(exc), status=409)
    except InvalidSignatureError as exc:
        status = 413 if "exceeds max size" in str(exc).lower() else 400
        return json_error(str(exc), status=status)
    return JsonResponse({
        "signature_file_path": intake_form.signature_file_path,
        "signature_sha256": intake_form.signature_sha256,
    })


@require_auth
def intake_form_anamnesis_view(request: HttpRequest, intake_form_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "TABLET"})
    if role_error:
        return role_error
    if request.method != "PUT":
        return json_error("Method not allowed.", status=405)

    try:
        body = UpdateAnamnesisPayloadRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        intake_form = save_intake_anamnesis_payload(
            intake_form_id=intake_form_id,
            anamnesis_schema_version=body.anamnesis_schema_version,
            answers_payload=[answer.model_dump() for answer in body.answers],
        )
    except ObjectDoesNotExist:
        return json_error("Intake form not found.", status=404)
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


@require_auth
def intake_form_submit_view(request: HttpRequest, intake_form_id: UUID) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"RECEPTION", "ADMIN", "TABLET"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        body = SubmitIntakeFormRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except InvalidRequestBodyEncoding:
        return json_error("Invalid request encoding.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        intake_form = submit_patient_intake_form(
            intake_form_id=intake_form_id,
            submitted_by_user_id=request.user.id,
        )
    except ObjectDoesNotExist:
        return json_error("Intake form not found.", status=404)
    except StateTransitionError as exc:
        return json_error(str(exc), status=400)
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
