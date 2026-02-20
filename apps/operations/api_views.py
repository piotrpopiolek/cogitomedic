from __future__ import annotations

from django.db import connection
from django.db.utils import Error as DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.api_utils import json_error, require_auth, require_user_role
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


@require_auth
def observability_metrics_view(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return json_error("Method not allowed.", status=405)
    role_error = require_user_role(request, allowed_roles={"ADMIN"})
    if role_error:
        return role_error

    payload = build_metrics_payload()
    return HttpResponse(payload, content_type="text/plain; version=0.0.4; charset=utf-8")
