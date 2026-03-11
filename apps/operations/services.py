from __future__ import annotations

import uuid
from typing import Any

from apps.operations.models import AuditEvent

# Reserved metadata key for immutable reference IDs (survive SET_NULL for compliance).
REF_KEY = "_ref"


def _build_metadata_with_ref(
    metadata: dict[str, Any] | None,
    *,
    actor_user_id: uuid.UUID | None,
    patient_id: uuid.UUID | None,
    medical_document_id: uuid.UUID | None,
    outbox_event_id: uuid.UUID | None,
    context_clinic_site_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Merge user metadata with immutable _ref copy of IDs for compliance after anonymization/deletion."""
    base = dict(metadata or {})
    ref: dict[str, str] = dict(base.get(REF_KEY) or {})
    if actor_user_id is not None:
        ref["actor_user_id"] = str(actor_user_id)
    if patient_id is not None:
        ref["patient_id"] = str(patient_id)
    if medical_document_id is not None:
        ref["medical_document_id"] = str(medical_document_id)
    if outbox_event_id is not None:
        ref["outbox_event_id"] = str(outbox_event_id)
    if context_clinic_site_id is not None:
        ref["context_clinic_site_id"] = str(context_clinic_site_id)
    if ref:
        base[REF_KEY] = ref
    return base


def create_audit_event(
    *,
    event_type: str,
    metadata: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    medical_document_id: uuid.UUID | None = None,
    outbox_event_id: uuid.UUID | None = None,
    context_clinic_site_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Persist a domain/operational audit event.

    IDs are stored as FKs and also copied into metadata['_ref'] so they survive
    SET_NULL on anonymization/deletion for compliance and support.
    """
    final_metadata = _build_metadata_with_ref(
        metadata,
        actor_user_id=actor_user_id,
        patient_id=patient_id,
        medical_document_id=medical_document_id,
        outbox_event_id=outbox_event_id,
        context_clinic_site_id=context_clinic_site_id,
    )
    return AuditEvent.objects.create(
        event_type=event_type,
        metadata=final_metadata,
        actor_user_id=actor_user_id,
        patient_id=patient_id,
        medical_document_id=medical_document_id,
        outbox_event_id=outbox_event_id,
        context_clinic_site_id=context_clinic_site_id,
    )
