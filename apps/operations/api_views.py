from __future__ import annotations

from datetime import timedelta

from django.db import connection
from django.db.utils import Error as DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone

from apps.core.api_utils import json_error, require_auth, require_user_role
from apps.operations.metrics import build_metrics_payload
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus


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
