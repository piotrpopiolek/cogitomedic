from __future__ import annotations

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_time = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=80)
    actor_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
    )
    patient = models.ForeignKey(
        "reception.Patient",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
    )
    medical_document = models.ForeignKey(
        "medical.MedicalDocument",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
    )
    outbox_event = models.ForeignKey(
        "outbox.OutboxEvent",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
    )
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "audit_event"
        constraints = [
            models.CheckConstraint(
                check=Q(metadata__isnull=False),
                name="audit_event_metadata_not_null",
            )
        ]
        indexes = [
            models.Index(fields=["-event_time"]),
            GinIndex(fields=["metadata"], name="audit_metadata_gin_idx", opclasses=["jsonb_path_ops"]),
        ]
