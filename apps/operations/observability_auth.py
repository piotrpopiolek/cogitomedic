"""Shared auth helpers for Prometheus / observability scrape endpoints."""

from __future__ import annotations

import hmac

from django.conf import settings


def bearer_authorized(authorization: str | None) -> bool:
    """True if ``Authorization`` matches ``Bearer <PROMETHEUS_METRICS_TOKEN>`` (constant-time)."""
    token = getattr(settings, "PROMETHEUS_METRICS_TOKEN", None)
    if not token or not authorization:
        return False
    expected = f"Bearer {token}"
    if len(authorization) != len(expected):
        return False
    return hmac.compare_digest(authorization, expected)
