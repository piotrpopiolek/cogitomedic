from __future__ import annotations

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from apps.core.translation_service import db_gettext_lazy
from django.db.models import F, Q


class OutboxEventType(models.TextChoices):
    GENERATE_PDF = "GENERATE_PDF", db_gettext_lazy("administration.choice_outbox_event_generate_pdf", "Generate PDF")
    HIDRIVE_UPLOAD = "HIDRIVE_UPLOAD", db_gettext_lazy("administration.choice_outbox_event_hidrive_upload", "HiDrive upload")
    SMS_SEND = "SMS_SEND", db_gettext_lazy("administration.choice_outbox_event_sms_send", "SMS send")


class OutboxStatus(models.TextChoices):
    PENDING = "PENDING", db_gettext_lazy("administration.choice_outbox_status_pending", "Pending")
    PROCESSING = "PROCESSING", db_gettext_lazy("administration.choice_outbox_status_processing", "Processing")
    PROCESSED = "PROCESSED", db_gettext_lazy("administration.choice_outbox_status_processed", "Processed")
    FAILED = "FAILED", db_gettext_lazy("administration.choice_outbox_status_failed", "Failed")
    DEAD_LETTER = "DEAD_LETTER", db_gettext_lazy("administration.choice_outbox_status_dead_letter", "Dead letter")


class OutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_document_version = models.ForeignKey(
        "medical.MedicalDocumentVersion",
        on_delete=models.CASCADE,
        related_name="outbox_events",
        verbose_name=db_gettext_lazy("administration.field_medical_document_version", "Medical document version"),
    )
    aggregate_type = models.CharField(max_length=50, default="MEDICAL_DOCUMENT_VERSION", verbose_name=db_gettext_lazy("administration.field_aggregate_type", "Aggregate type"))
    aggregate_id = models.UUIDField(verbose_name=db_gettext_lazy("administration.field_aggregate_id", "Aggregate ID"))
    event_type = models.CharField(max_length=30, choices=OutboxEventType.choices, verbose_name=db_gettext_lazy("administration.field_event_type", "Event type"))
    payload_schema_version = models.SmallIntegerField(default=1, verbose_name=db_gettext_lazy("administration.field_payload_schema_version", "Payload schema version"))
    payload = models.JSONField(verbose_name=db_gettext_lazy("administration.field_payload", "Payload"))
    status = models.CharField(max_length=20, choices=OutboxStatus.choices, default=OutboxStatus.PENDING, verbose_name=db_gettext_lazy("administration.field_status", "Status"))
    retry_count = models.SmallIntegerField(default=0, verbose_name=db_gettext_lazy("administration.field_retry_count", "Retry count"))
    max_retries = models.SmallIntegerField(default=10, verbose_name=db_gettext_lazy("administration.field_max_retries", "Max retries"))
    available_at = models.DateTimeField(auto_now_add=True, verbose_name=db_gettext_lazy("administration.field_available_at", "Available at"))
    locked_at = models.DateTimeField(blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_locked_at", "Locked at"))
    processed_at = models.DateTimeField(blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_processed_at", "Processed at"))
    error_message = models.TextField(blank=True, null=True, verbose_name=db_gettext_lazy("administration.field_error_message", "Error message"))
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=db_gettext_lazy("administration.field_created_at", "Created at"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=db_gettext_lazy("administration.field_updated_at", "Updated at"),
    )

    class Meta:
        db_table = "outbox_event"
        constraints = [
            models.UniqueConstraint(
                fields=["medical_document_version", "event_type"],
                name="outbox_event_unique_per_type",
            ),
            models.CheckConstraint(
                condition=Q(retry_count__gte=0)
                & Q(max_retries__gt=0)
                & Q(retry_count__lte=F("max_retries")),
                name="outbox_event_retry_bounds",
            ),
            models.CheckConstraint(
                condition=Q(aggregate_type="MEDICAL_DOCUMENT_VERSION"),
                name="outbox_event_aggregate_type_guard",
            ),
            models.CheckConstraint(
                condition=Q(aggregate_id=F("medical_document_version_id")),
                name="outbox_event_aggregate_id_guard",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "available_at"]),
            models.Index(fields=["event_type", "status", "retry_count", "available_at", "payload_schema_version"]),
            models.Index(fields=["medical_document_version", "-created_at"]),
            models.Index(
                fields=["status", "available_at"],
                name="outbox_pend_fail_idx",
                condition=Q(status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED]),
            ),
            # Worker query: ORDER BY available_at, created_at; index scan in exact order, no extra sort.
            models.Index(
                fields=["available_at", "created_at"],
                name="outbox_pend_fail_order_idx",
                condition=Q(status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED]),
            ),
            GinIndex(
                fields=["payload"],
                name="outbox_payload_gin_idx",
                opclasses=["jsonb_path_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} – wersja {self.medical_document_version} ({self.get_status_display()})"
