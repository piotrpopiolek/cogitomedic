"""HTTP helpers (client IP behind reverse proxy)."""

from __future__ import annotations

from django.http import HttpRequest


def get_client_ip(request: HttpRequest) -> str | None:
    """
    Best-effort client IP for audit logs.

    Uses X-Forwarded-For first hop when present (configure trusted proxy at the edge);
    otherwise REMOTE_ADDR.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first[:45]
    addr = request.META.get("REMOTE_ADDR")
    if addr:
        return str(addr)[:45]
    return None
