"""Production gate: TELEDERM queue entries only when explicitly enabled."""

from __future__ import annotations

from django.conf import settings

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.reception.process_types import PROCESS_TYPE_TELEDERM


def telederm_intake_enabled() -> bool:
    return bool(getattr(settings, "TELEDERM_INTAKE_ENABLED", False))


def assert_telederm_creation_allowed(process_type: str) -> None:
    if process_type == PROCESS_TYPE_TELEDERM and not telederm_intake_enabled():
        raise DomainError(
            domain_message("other.domain.telederm_intake_disabled"),
            api_message_key="other.domain.telederm_intake_disabled",
        )
