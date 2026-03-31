from __future__ import annotations

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from apps.core.translation_service import db_gettext_lazy
from django.db.models import Q


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_time = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_event_time", "Event time"),
    )
    event_type = models.CharField(
        max_length=80,
        verbose_name=db_gettext_lazy("administration.field_event_type", "Event type"),
    )
    actor_user = models.ForeignKey(
        "users.StaffUser",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
        verbose_name=db_gettext_lazy("administration.field_actor_user", "Actor user"),
    )
    patient = models.ForeignKey(
        "reception.Patient",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
        verbose_name=db_gettext_lazy("administration.field_patient", "Patient"),
    )
    medical_document = models.ForeignKey(
        "medical.MedicalDocument",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
        verbose_name=db_gettext_lazy(
            "administration.field_medical_document", "Medical document"
        ),
    )
    outbox_event = models.ForeignKey(
        "outbox.OutboxEvent",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
        verbose_name=db_gettext_lazy(
            "administration.field_outbox_event", "Outbox event"
        ),
    )
    context_clinic_site = models.ForeignKey(
        "reception.ClinicSite",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
        verbose_name=db_gettext_lazy(
            "administration.field_context_clinic_site", "Context clinic site"
        ),
    )
    metadata = models.JSONField(
        default=dict,
        verbose_name=db_gettext_lazy("administration.field_metadata", "Metadata"),
    )

    class Meta:
        db_table = "audit_event"
        constraints = [
            models.CheckConstraint(
                condition=Q(metadata__isnull=False),
                name="audit_event_metadata_not_null",
            )
        ]
        indexes = [
            models.Index(fields=["-event_time"]),
            GinIndex(
                fields=["metadata"],
                name="audit_metadata_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
            models.Index(
                fields=["patient_id", "-event_time"],
                name="audit_event_patient_time_idx",
            ),
            models.Index(
                fields=["medical_document_id", "-event_time"],
                name="audit_event_doc_time_idx",
            ),
            models.Index(
                fields=["context_clinic_site_id", "-event_time"],
                name="audit_event_clinic_time_idx",
            ),
            models.Index(
                fields=["outbox_event_id", "-event_time"],
                name="audit_event_outbox_time_idx",
            ),
        ]

    def __str__(self) -> str:
        actor = str(self.actor_user) if self.actor_user_id else "—"
        return f"{self.event_type} – {self.event_time.strftime('%d.%m.%Y')} ({actor})"
