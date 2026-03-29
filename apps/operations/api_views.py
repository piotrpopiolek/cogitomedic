from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.db.utils import Error as DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.dateparse import parse_datetime

from apps.operations.services import REF_KEY
from apps.core.api_utils import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    json_error,
    require_auth,
    require_user_role,
    safe_parse_positive_int,
)
from apps.operations.metrics import build_metrics_payload
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

    qs = AuditEvent.objects.all().order_by("-event_time")

    if request.user.is_doctor:
        # DOCTOR: only events where metadata.assigned_doctor_id == current_user.id
        # OR actor_user_id == current_user.id
        qs = qs.filter(
            Q(metadata__assigned_doctor_id=str(request.user.id))
            | Q(metadata__actor_user_id=str(request.user.id))
            | Q(actor_user_id=request.user.id)
        )

    event_type = request.GET.get("event_type")
    if event_type:
        qs = qs.filter(event_type=event_type)

    patient_id = request.GET.get("patient_id")
    if patient_id:
        qs = qs.filter(patient_id=patient_id)

    medical_document_id = request.GET.get("medical_document_id")
    if medical_document_id:
        try:
            qs = qs.filter(medical_document_id=uuid.UUID(medical_document_id))
        except (ValueError, TypeError):
            pass

    context_clinic_site_id = request.GET.get("context_clinic_site_id")
    if context_clinic_site_id:
        try:
            qs = qs.filter(context_clinic_site_id=uuid.UUID(context_clinic_site_id))
        except (ValueError, TypeError):
            pass

    actor_user_id = request.GET.get("actor_user_id")
    if actor_user_id:
        try:
            qs = qs.filter(actor_user_id=uuid.UUID(actor_user_id))
        except (ValueError, TypeError):
            pass

    outbox_event_id = request.GET.get("outbox_event_id")
    if outbox_event_id:
        try:
            qs = qs.filter(outbox_event_id=uuid.UUID(outbox_event_id))
        except (ValueError, TypeError):
            pass

    from_time = request.GET.get("from")
    if from_time:
        parsed = parse_datetime(from_time)
        if parsed:
            qs = qs.filter(event_time__gte=parsed)

    to_time = request.GET.get("to")
    if to_time:
        parsed = parse_datetime(to_time)
        if parsed:
            qs = qs.filter(event_time__lte=parsed)

    page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
    page_size = safe_parse_positive_int(
        request.GET.get("page_size"),
        default=DEFAULT_LIST_LIMIT,
        maximum=MAX_LIST_LIMIT,
    )

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = [_serialize_audit_event(e) for e in qs[start:end]]

    return JsonResponse(
        {
            "items": items,
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }
    )


def _observability_authorized(request: HttpRequest) -> bool:
    """True if request is authorized for detailed observability (Bearer token or ADMIN)."""
    token = getattr(settings, "PROMETHEUS_METRICS_TOKEN", None)
    if token and request.headers.get("Authorization") == f"Bearer {token}":
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
