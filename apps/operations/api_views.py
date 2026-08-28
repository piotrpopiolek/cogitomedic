from __future__ import annotations

from typing import Any

from django.db import connection
from django.db.models import Q
from django.db.utils import Error as DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.dateparse import parse_datetime
from pydantic import ValidationError

from apps.operations.services import REF_KEY
from apps.core.api_utils import (
    json_error,
    json_pydantic_query_validation_error,
    require_auth,
    require_user_role,
    validate_get_query_params,
)
from apps.operations.api_schemas import AuditEventsListQueryParams
from apps.operations.metrics import build_metrics_payload
from apps.operations.observability_auth import bearer_authorized
from apps.operations.models import AuditEvent


def _ref(event: AuditEvent, key: str) -> str | None:
    """Return immutable ref from metadata when FK was nulled (compliance)."""
    ref = (event.metadata or {}).get(REF_KEY) or {}
    return ref.get(key)


def _serialize_audit_event(event: AuditEvent) -> dict[str, Any]:
    """Serialize event; use metadata._ref for IDs when FK is null (after anonymization/deletion)."""
    return {
        "id": str(event.id),
        "event_time": event.event_time.isoformat(),
        "event_type": event.event_type,
        "actor_user_id": (
            str(event.actor_user_id)
            if event.actor_user_id
            else _ref(event, "actor_user_id")
        ),
        "patient_id": (
            str(event.patient_id) if event.patient_id else _ref(event, "patient_id")
        ),
        "medical_document_id": (
            str(event.medical_document_id)
            if event.medical_document_id
            else _ref(event, "medical_document_id")
        ),
        "outbox_event_id": (
            str(event.outbox_event_id)
            if event.outbox_event_id
            else _ref(event, "outbox_event_id")
        ),
        "context_clinic_site_id": (
            str(event.context_clinic_site_id)
            if event.context_clinic_site_id
            else _ref(event, "context_clinic_site_id")
        ),
        "metadata": event.metadata,
    }


@require_auth
def audit_events_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN", "DOCTOR"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)

    try:
        query = validate_get_query_params(AuditEventsListQueryParams, request.GET)
    except ValidationError as exc:
        return json_pydantic_query_validation_error(exc)

    qs = AuditEvent.objects.all().order_by("-event_time")

    if request.user.is_doctor:
        # DOCTOR: only events where metadata.assigned_doctor_id == current_user.id
        # OR actor_user_id == current_user.id
        qs = qs.filter(
            Q(metadata__assigned_doctor_id=str(request.user.id))
            | Q(metadata__actor_user_id=str(request.user.id))
            | Q(actor_user_id=request.user.id)
        )

    if query.event_type:
        qs = qs.filter(event_type=query.event_type)

    if query.patient_id:
        qs = qs.filter(patient_id=query.patient_id)

    if query.medical_document_id:
        qs = qs.filter(medical_document_id=query.medical_document_id)

    if query.context_clinic_site_id:
        qs = qs.filter(context_clinic_site_id=query.context_clinic_site_id)

    if query.actor_user_id:
        qs = qs.filter(actor_user_id=query.actor_user_id)

    if query.outbox_event_id:
        qs = qs.filter(outbox_event_id=query.outbox_event_id)

    if query.from_:
        parsed = parse_datetime(query.from_)
        if parsed:
            qs = qs.filter(event_time__gte=parsed)

    if query.to_:
        parsed = parse_datetime(query.to_)
        if parsed:
            qs = qs.filter(event_time__lte=parsed)

    total = qs.count()
    start = (query.page - 1) * query.page_size
    end = start + query.page_size
    items = [_serialize_audit_event(e) for e in qs[start:end]]

    return JsonResponse(
        {
            "items": items,
            "pagination": {
                "page": query.page,
                "page_size": query.page_size,
                "total": total,
            },
        }
    )


def _observability_authorized(request: HttpRequest) -> bool:
    """True if request is authorized for detailed observability (Bearer token or ADMIN)."""
    if bearer_authorized(request.headers.get("Authorization")):
        return True
    if (
        request.user.is_authenticated
        and require_user_role(request, allowed_roles={"ADMIN"}) is None
    ):
        return True
    return False


def observability_health_view(request: HttpRequest) -> JsonResponse:
    """Health check for load balancers/Docker. Anonymous gets minimal response (no internal checks leak)."""
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)

    http_status = 200
    try:
        connection.ensure_connection()
    except DatabaseError:
        http_status = 503

    status_value = "ok" if http_status == 200 else "error"
    if _observability_authorized(request):
        payload = {
            "status": status_value,
            "checks": {
                "db": "ok" if http_status == 200 else "error",
                "hidrive": "unknown",
                "sms": "unknown",
            },
        }
    else:
        payload = {"status": status_value}
    return JsonResponse(payload, status=http_status)


def observability_metrics_view(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return json_error("other.api.method_not_allowed", status=405)

    if not _observability_authorized(request):
        return json_error("other.api.unauthorized", status=401)

    payload = build_metrics_payload()
    return HttpResponse(
        payload, content_type="text/plain; version=0.0.4; charset=utf-8"
    )
