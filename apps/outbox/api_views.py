from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from pydantic import ValidationError

from apps.core.api_utils import (
    get_scoped_clinic_site_ids,
    json_domain_error,
    json_error,
    json_pydantic_query_validation_error,
    read_json_body,
    require_auth,
    require_user_role,
    validate_get_query_params,
)
from apps.core.http_utils import get_client_ip
from apps.operations.services import create_audit_event
from apps.core.exceptions import DomainError, InvalidRequestBodyEncoding
from apps.outbox.api_schemas import (
    OutboxEventsQueryParams,
    ProcessOutboxRequest,
    RetentionRunRequest,
    RetryOutboxEventRequest,
)
from apps.outbox.models import OutboxEvent
from apps.intake.retention_services import run_intake_retention_cleanup
from apps.outbox.services import (
    process_outbox_events,
    retry_outbox_event,
    run_retention_cleanup,
)


@require_auth
def outbox_events_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"ADMIN", "MANAGER", "RECEPTION"}
    )
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        body = validate_get_query_params(OutboxEventsQueryParams, request.GET)
    except ValidationError as exc:
        return json_pydantic_query_validation_error(exc)

    qs = OutboxEvent.objects.select_related(
        "medical_document_version__medical_document__queue_entry__daily_queue"
    ).order_by("-created_at")
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    if scoped_clinic_site_ids is not None:
        qs = qs.filter(
            medical_document_version__medical_document__queue_entry__daily_queue__clinic_site_id__in=scoped_clinic_site_ids
        )
    if body.status:
        qs = qs.filter(status=body.status)
    if body.event_type:
        qs = qs.filter(event_type=body.event_type)
    qs = qs.filter(retry_count__gte=body.retry_count_gte)[: body.limit]

    events = [
        {
            "id": str(event.id),
            "medical_document_version_id": str(event.medical_document_version_id),
            "event_type": event.event_type,
            "status": event.status,
            "retry_count": event.retry_count,
            "max_retries": event.max_retries,
            "available_at": (
                event.available_at.isoformat() if event.available_at else None
            ),
            "error_message": event.error_message,
        }
        for event in qs
    ]
    return JsonResponse({"results": events, "count": len(events)}, status=200)


@require_auth
def operations_outbox_process_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        body = ProcessOutboxRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return JsonResponse(
            {"error": "Validation error.", "details": exc.errors()}, status=400
        )

    create_audit_event(
        event_type="OPERATIONS_OUTBOX_BATCH_TRIGGERED",
        actor_user_id=request.user.id,
        metadata={
            "limit": body.limit,
            "client_ip": get_client_ip(request),
        },
    )
    result = process_outbox_events(batch_size=body.limit)
    return JsonResponse(
        {
            "processed": result.processed,
            "failed": result.failed,
            "dead_lettered": result.dead_lettered,
        },
        status=202,
    )


@require_auth
def outbox_event_retry_view(
    request: HttpRequest, outbox_event_id: UUID
) -> JsonResponse:
    role_error = require_user_role(
        request, allowed_roles={"ADMIN", "MANAGER", "RECEPTION"}
    )
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        body = RetryOutboxEventRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return JsonResponse(
            {"error": "Validation error.", "details": exc.errors()}, status=400
        )

    try:
        event = OutboxEvent.objects.select_related(
            "medical_document_version__medical_document__queue_entry__daily_queue"
        ).get(id=outbox_event_id)
    except ObjectDoesNotExist:
        return json_error("other.api.outbox_event_not_found", status=404)
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(request.user)
    if (
        scoped_clinic_site_ids is not None
        and event.medical_document_version.medical_document.queue_entry.daily_queue.clinic_site_id
        not in scoped_clinic_site_ids
    ):
        return json_error("other.api.outbox_event_not_found", status=404)

    try:
        retried = retry_outbox_event(
            event=event,
            reason=body.reason,
            actor_user_id=request.user.id,
        )
    except DomainError as exc:
        return json_domain_error(exc, status=409)

    return JsonResponse(
        {
            "id": str(retried.id),
            "status": retried.status,
            "retry_count": retried.retry_count,
        },
        status=200,
    )


@require_auth
def operations_retention_run_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN"})
    if role_error:
        return role_error
    if request.method != "POST":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        body = RetentionRunRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("other.api.invalid_json_payload", status=400)
    except InvalidRequestBodyEncoding as exc:
        return json_domain_error(exc)
    except ValidationError as exc:
        return JsonResponse(
            {"error": "Validation error.", "details": exc.errors()}, status=400
        )

    create_audit_event(
        event_type="OPERATIONS_RETENTION_RUN_TRIGGERED",
        actor_user_id=request.user.id,
        metadata={
            "older_than_days": body.older_than_days,
            "dry_run": body.dry_run,
            "client_ip": get_client_ip(request),
        },
    )
    try:
        befund_result = run_retention_cleanup(
            older_than_days=body.older_than_days,
            dry_run=body.dry_run,
        )
        intake_result = run_intake_retention_cleanup(
            older_than_days=body.older_than_days,
            dry_run=body.dry_run,
        )
    except DomainError as exc:
        return json_domain_error(exc, status=400)

    return JsonResponse(
        {
            "befund": {
                "candidates": befund_result.candidates,
                "deleted": befund_result.deleted,
                "skipped_not_safe": befund_result.skipped_not_safe,
            },
            "intake": {
                "candidates": intake_result.candidates,
                "deleted": intake_result.deleted,
                "skipped_not_safe": intake_result.skipped_not_safe,
            },
        },
        status=202,
    )
