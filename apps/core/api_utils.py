from __future__ import annotations

import json

from django.http import HttpRequest
from django.http import JsonResponse


def json_error(message: str, *, status: int) -> JsonResponse:
    """Build a normalized JSON error response payload."""
    return JsonResponse({"error": message}, status=status)


def read_json_body(request: HttpRequest) -> dict:
    """Decode JSON body for API views (raises JSONDecodeError on invalid input)."""
    return json.loads(request.body.decode("utf-8") or "{}")
