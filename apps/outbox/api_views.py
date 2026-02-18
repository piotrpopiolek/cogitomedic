from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body, require_auth
from apps.core.exceptions import DomainError
from apps.outbox.api_schemas import (
    OutboxEventsQueryParams,
    ProcessOutboxRequest,
    RetentionRunRequest,
    RetryOutboxEventRequest,
)
from apps.outbox.models import OutboxEvent
from apps.outbox.services import process_outbox_events, retry_outbox_event, run_retention_cleanup

@require_auth
def outbox_events_view(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)

    raw_retry_count_gte = request.GET.get("retry_count_gte")
    raw_limit = request.GET.get("limit")
    try:
        retry_count_gte = int(raw_retry_count_gte) if raw_retry_count_gte not in (None, "") else 0
        limit = int(raw_limit) if raw_limit not in (None, "") else 50
    except ValueError:
        return json_error("retry_count_gte and limit must be integers.", status=400)

    try:
        body = OutboxEventsQueryParams.model_validate(
            {
                "status": request.GET.get("status"),
                "event_type": request.GET.get("event_type"),
                "retry_count_gte": retry_count_gte,
                "limit": limit,
            }
        )
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    qs = OutboxEvent.objects.order_by("-created_at")
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
            "available_at": event.available_at.isoformat() if event.available_at else None,
            "error_message": event.error_message,
        }
        for event in qs
    ]
    return JsonResponse({"results": events, "count": len(events)}, status=200)


@require_auth
@csrf_exempt
def operations_outbox_process_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        body = ProcessOutboxRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

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
@csrf_exempt
def outbox_event_retry_view(request: HttpRequest, outbox_event_id: UUID) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        body = RetryOutboxEventRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        event = OutboxEvent.objects.get(id=outbox_event_id)
    except ObjectDoesNotExist:
        return json_error("Outbox event not found.", status=404)

    try:
        retried = retry_outbox_event(event=event, reason=body.reason)
    except DomainError as exc:
        return json_error(str(exc), status=409)

    return JsonResponse(
        {
            "id": str(retried.id),
            "status": retried.status,
            "retry_count": retried.retry_count,
        },
        status=200,
    )


@require_auth
@csrf_exempt
def operations_retention_run_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        body = RetentionRunRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        result = run_retention_cleanup(
            older_than_days=body.older_than_days,
            dry_run=body.dry_run,
        )
    except DomainError as exc:
        return json_error(str(exc), status=400)

    return JsonResponse(
        {
            "candidates": result.candidates,
            "deleted": result.deleted,
            "skipped_not_safe": result.skipped_not_safe,
        },
        status=202,
    )
