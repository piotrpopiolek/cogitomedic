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


def parse_bool_query(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def parse_positive_int(value: str, *, default: int, minimum: int = 1, maximum: int = 100) -> int:
    if not value:
        return default
    parsed = int(value)
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def require_authenticated_user(request: HttpRequest) -> JsonResponse | None:
    """Return normalized 401 error response when user is not authenticated."""
    if not request.user.is_authenticated:
        return json_error("Authentication required.", status=401)
    return None


def require_user_role(request: HttpRequest, *, allowed_roles: set[str]) -> JsonResponse | None:
    """Return normalized 403 when authenticated user role is not allowed."""
    role = getattr(request.user, "role", None)
    if role not in allowed_roles:
        return json_error("Forbidden.", status=403)
    return None
