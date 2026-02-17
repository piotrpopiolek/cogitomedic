from __future__ import annotations

import uuid
from typing import Any

from apps.operations.models import AuditEvent


def create_audit_event(
    *,
    event_type: str,
    metadata: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    medical_document_id: uuid.UUID | None = None,
    outbox_event_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Persist a domain/operational audit event."""
    return AuditEvent.objects.create(
        event_type=event_type,
        metadata=metadata or {},
        actor_user_id=actor_user_id,
        patient_id=patient_id,
        medical_document_id=medical_document_id,
        outbox_event_id=outbox_event_id,
    )
