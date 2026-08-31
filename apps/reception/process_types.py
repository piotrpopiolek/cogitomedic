"""Queue / catalog process type (STANDARD, TELEDERM)."""

from __future__ import annotations

from django.db import models

from apps.core.translation_service import db_gettext_lazy

QUEUE_ENTRY_PROCESS_TYPE_UNIQUE = "queue_entry_process_type_unique"


class ProcessType(models.TextChoices):
    STANDARD = "STANDARD", db_gettext_lazy(
        "administration.choice_process_type_standard",
        "Standard",
    )
    TELEDERM = "TELEDERM", db_gettext_lazy(
        "administration.choice_process_type_telederm",
        "Teledermatology",
    )


def coerce_process_type(value: str | None) -> str:
    """Return a valid process type; unknown or empty → STANDARD (tablet fallback)."""
    if value in ProcessType.values:
        return str(value)
    return ProcessType.STANDARD.value
