"""Shared JSON payloads for retention / anonymization (schema_version required by project rules)."""

from __future__ import annotations

RETENTION_CLEARED_MEDICAL_PAYLOAD: dict = {"schema_version": 1, "cleared_at_retention": True}
RETENTION_CLEARED_INTAKE_SNAPSHOT: dict = {"schema_version": 1, "cleared_at_retention": True}
ANONYMIZED_INTAKE_SNAPSHOT: dict = {"schema_version": 1, "anonymized": True}
