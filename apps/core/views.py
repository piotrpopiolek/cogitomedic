"""Shared views used by middleware or URLconf (e.g. rate limit 429)."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse

from apps.core.api_utils import json_error


def ratelimited_view(request: HttpRequest, exception: Exception) -> JsonResponse:
    """Return 429 JSON when rate limit is exceeded. Used by RATELIMIT_VIEW."""
    return json_error("Too many requests. Try again later.", status=429)
