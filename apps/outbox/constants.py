"""Outbox configuration helpers."""

from __future__ import annotations

from django.conf import settings


def outbox_max_retries_default() -> int:
    """Default max_retries for new outbox rows (``OUTBOX_MAX_RETRIES`` in settings)."""
    return int(settings.OUTBOX_MAX_RETRIES)
