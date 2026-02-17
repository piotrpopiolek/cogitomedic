from __future__ import annotations

from django.http import JsonResponse


def json_error(message: str, *, status: int) -> JsonResponse:
    """Build a normalized JSON error response payload."""
    return JsonResponse({"error": message}, status=status)
