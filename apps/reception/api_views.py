from __future__ import annotations

from json import JSONDecodeError
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import ValidationError

from apps.core.api_utils import json_error, read_json_body
from apps.core.exceptions import DomainError
from apps.reception.api_schemas import CreateQueueEntrySessionRequest
from apps.reception.services import issue_tablet_session_token_latest_wins


@csrf_exempt
def queue_entry_sessions_view(request: HttpRequest, queue_entry_id: UUID) -> JsonResponse:
    if request.method != "POST":
        return json_error("Method not allowed.", status=405)

    try:
        body = CreateQueueEntrySessionRequest.model_validate(read_json_body(request))
    except JSONDecodeError:
        return json_error("Invalid JSON payload.", status=400)
    except ValidationError as exc:
        return JsonResponse({"error": "Validation error.", "details": exc.errors()}, status=400)

    try:
        issued = issue_tablet_session_token_latest_wins(
            queue_entry_id=queue_entry_id,
            created_by_user_id=body.created_by_user_id,
            form_locale=body.form_locale,
            expires_in_minutes=body.expires_in_minutes,
            tablet_device_id=body.tablet_device_id,
        )
    except ObjectDoesNotExist:
        return json_error("Queue entry or tablet device not found.", status=404)
    except DomainError as exc:
        return json_error(str(exc), status=400)

    return JsonResponse(
        {
            "token": issued.token_plain,
            "session_id": str(issued.session_id),
            "expires_at": issued.expires_at.isoformat(),
        },
        status=201,
    )
