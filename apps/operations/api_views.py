from __future__ import annotations

from django.http import HttpResponse
from django.db import connection
from django.db.utils import Error as DatabaseError
from django.http import HttpRequest, JsonResponse

from apps.core.api_utils import json_error
from apps.operations.metrics import build_metrics_payload
from apps.outbox.models import OutboxEvent, OutboxStatus


def observability_health_view(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)

    db_status = "ok"
    outbox_tasks_status = "ok"
    http_status = 200

    try:
        connection.ensure_connection()
    except DatabaseError:
        db_status = "error"
        http_status = 503

    if db_status == "ok":
        pending_count = OutboxEvent.objects.filter(status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED]).count()
        if pending_count > 0:
            outbox_tasks_status = "degraded"

    payload = {
        "status": "ok" if http_status == 200 else "degraded",
        "checks": {
            "db": db_status,
            "outbox_tasks": outbox_tasks_status,
            "hidrive": "unknown",
            "sms": "unknown",
        },
    }
    return JsonResponse(payload, status=http_status)


def observability_metrics_view(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)

    payload = build_metrics_payload()
    return HttpResponse(payload, content_type="text/plain; version=0.0.4; charset=utf-8")
