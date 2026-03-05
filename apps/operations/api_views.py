from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.db.utils import Error as DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from pydantic import BaseModel, ConfigDict

from apps.core.api_utils import json_error, parse_list_limit, require_auth, require_user_role, safe_parse_positive_int
from apps.operations.metrics import build_metrics_payload
from apps.operations.models import AuditEvent
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus


def _serialize_audit_event(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "event_time": event.event_time.isoformat(),
        "event_type": event.event_type,
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "patient_id": str(event.patient_id) if event.patient_id else None,
        "medical_document_id": str(event.medical_document_id) if event.medical_document_id else None,
        "outbox_event_id": str(event.outbox_event_id) if event.outbox_event_id else None,
        "context_clinic_site_id": str(event.context_clinic_site_id) if event.context_clinic_site_id else None,
        "metadata": event.metadata,
    }


@require_auth
def audit_events_view(request: HttpRequest) -> JsonResponse:
    role_error = require_user_role(request, allowed_roles={"ADMIN", "DOCTOR"})
    if role_error:
        return role_error
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)

    qs = AuditEvent.objects.all().order_by("-event_time")
    
    if request.user.is_doctor:
        # DOCTOR: only events where metadata.assigned_doctor_id == current_user.id
        # OR actor_user_id == current_user.id
        qs = qs.filter(
            Q(metadata__assigned_doctor_id=str(request.user.id)) |
            Q(metadata__actor_user_id=str(request.user.id)) |
            Q(actor_user_id=request.user.id)
        )

    event_type = request.GET.get("event_type")
    if event_type:
        qs = qs.filter(event_type=event_type)

    patient_id = request.GET.get("patient_id")
    if patient_id:
        qs = qs.filter(patient_id=patient_id)

    medical_document_id = request.GET.get("medical_document_id")
    if medical_document_id:
        qs = qs.filter(medical_document_id=medical_document_id)

    page = safe_parse_positive_int(request.GET.get("page"), default=1, maximum=10_000)
    page_size = safe_parse_positive_int(request.GET.get("page_size"), default=20, maximum=200)

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


def observability_health_view(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)

    db_status = "ok"
    http_status = 200

    try:
        connection.ensure_connection()
    except DatabaseError:
        db_status = "error"
        http_status = 503

    payload = {
        "status": "ok" if http_status == 200 else "error",
        "checks": {
            "db": db_status,
            "hidrive": "unknown",
            "sms": "unknown",
        },
    }
    return JsonResponse(payload, status=http_status)


def observability_metrics_view(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
        
    auth_header = request.headers.get("Authorization", "")
    token = getattr(settings, "PROMETHEUS_METRICS_TOKEN", None)
    
    if token and auth_header == f"Bearer {token}":
        pass  # Token valid
    else:
        # Fallback to ADMIN session if token is not provided/invalid
        if not request.user.is_authenticated:
            return json_error("Unauthorized.", status=401)
        role_error = require_user_role(request, allowed_roles={"ADMIN"})
        if role_error:
            return role_error

    payload = build_metrics_payload()
    return HttpResponse(payload, content_type="text/plain; version=0.0.4; charset=utf-8")
