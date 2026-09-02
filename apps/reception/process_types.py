"""Queue / catalog process type (STANDARD, TELEDERM)."""

from __future__ import annotations

from django.db import models
from django.db.models import CheckConstraint, Q

from apps.core.translation_service import db_gettext_lazy

QUEUE_ENTRY_PROCESS_TYPE_UNIQUE = "queue_entry_process_type_unique"
QUEUE_ENTRY_PROCESS_TYPE_ALLOWED = "queue_entry_process_type_allowed"
CONSENT_DEFINITION_PROCESS_TYPE_ALLOWED = "consent_definition_process_type_allowed"
ANAMNESIS_QUESTION_PROCESS_TYPE_ALLOWED = "anamnesis_question_process_type_allowed"


PROCESS_TYPE_STANDARD = "STANDARD"
PROCESS_TYPE_TELEDERM = "TELEDERM"
PROCESS_TYPE_VALUES = (PROCESS_TYPE_STANDARD, PROCESS_TYPE_TELEDERM)


class ProcessType(models.TextChoices):
    STANDARD = PROCESS_TYPE_STANDARD, db_gettext_lazy(
        "administration.choice_process_type_standard",
        "Standard",
    )
    TELEDERM = PROCESS_TYPE_TELEDERM, db_gettext_lazy(
        "administration.choice_process_type_telederm",
        "Teledermatology",
    )


def process_type_allowed_constraint(*, name: str) -> CheckConstraint:
    """DB CHECK: process_type IN (STANDARD, TELEDERM)."""
    return CheckConstraint(
        condition=Q(process_type__in=PROCESS_TYPE_VALUES),
        name=name,
    )


def coerce_process_type(value: str | None) -> str:
    """Return a valid process type; unknown or empty → STANDARD (tablet fallback)."""
    if value in ProcessType.values:
        return str(value)
    return PROCESS_TYPE_STANDARD
