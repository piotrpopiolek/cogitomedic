from __future__ import annotations

from datetime import timedelta
from typing import Any

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
    
    if getattr(request.user, "role", None) == "DOCTOR":
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
    outbox_tasks_status = "ok"
    http_status = 200
    alerts: list[dict] = []

    try:
        connection.ensure_connection()
    except DatabaseError:
        db_status = "error"
        http_status = 503

    if db_status == "ok":
        pending_count = OutboxEvent.objects.filter(status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED]).count()
        if pending_count > 0:
            outbox_tasks_status = "degraded"
        oldest_pending = (
            OutboxEvent.objects.filter(status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED])
            .order_by("created_at")
            .first()
        )
        if oldest_pending is not None:
            oldest_age = (timezone.now() - oldest_pending.created_at).total_seconds()
            if oldest_age > 900:
                alerts.append(
                    {
                        "severity": "critical",
                        "code": "OUTBOX_BACKLOG_AGE",
                        "message": "Oldest pending/failed outbox event is older than 900s.",
                        "value_seconds": oldest_age,
                    }
                )
        ten_minutes_ago = timezone.now() - timedelta(minutes=10)
        for event_type in [OutboxEventType.HIDRIVE_UPLOAD, OutboxEventType.SMS_SEND]:
            has_failed = OutboxEvent.objects.filter(
                event_type=event_type,
                status__in=[OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER],
                updated_at__lte=ten_minutes_ago,
            ).exists()
            if has_failed:
                alerts.append(
                    {
                        "severity": "critical",
                        "code": f"{event_type}_FAILED_OVER_10M",
                        "message": f"{event_type} has FAILED/DEAD_LETTER events for >10 minutes.",
                    }
                )

        one_hour_ago = timezone.now() - timedelta(hours=1)
        for event_type in [OutboxEventType.HIDRIVE_UPLOAD, OutboxEventType.SMS_SEND]:
            terminal = OutboxEvent.objects.filter(
                event_type=event_type,
                created_at__gte=one_hour_ago,
                status__in=[OutboxStatus.PROCESSED, OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER],
            )
            total = terminal.count()
            if total == 0:
                continue
            success = terminal.filter(status=OutboxStatus.PROCESSED).count()
            ratio = success / total
            if ratio < 0.98:
                alerts.append(
                    {
                        "severity": "warning",
                        "code": f"{event_type}_SUCCESS_RATIO_LOW",
                        "message": f"{event_type} success ratio below 98% in 1h window.",
                        "ratio": ratio,
                    }
                )

    payload = {
        "status": "ok" if http_status == 200 else "degraded",
        "checks": {
            "db": db_status,
            "outbox_tasks": outbox_tasks_status,
            "hidrive": "unknown",
            "sms": "unknown",
        },
        "alerts": alerts,
    }
    return JsonResponse(payload, status=http_status)


@require_auth
def observability_metrics_view(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    role_error = require_user_role(request, allowed_roles={"ADMIN"})
    if role_error:
        return role_error

    payload = build_metrics_payload()
    return HttpResponse(payload, content_type="text/plain; version=0.0.4; charset=utf-8")
