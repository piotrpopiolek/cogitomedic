from __future__ import annotations

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q


class OutboxEventType(models.TextChoices):
    GENERATE_PDF = "GENERATE_PDF", "Generate PDF"
    HIDRIVE_UPLOAD = "HIDRIVE_UPLOAD", "HiDrive upload"
    SMS_SEND = "SMS_SEND", "SMS send"


class OutboxStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    PROCESSED = "PROCESSED", "Processed"
    FAILED = "FAILED", "Failed"
    DEAD_LETTER = "DEAD_LETTER", "Dead letter"


class OutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medical_document_version = models.ForeignKey(
        "medical.MedicalDocumentVersion",
        on_delete=models.CASCADE,
        related_name="outbox_events",
    )
    aggregate_type = models.CharField(max_length=50, default="MEDICAL_DOCUMENT_VERSION")
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=30, choices=OutboxEventType.choices)
    payload_schema_version = models.SmallIntegerField(default=1)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=OutboxStatus.choices, default=OutboxStatus.PENDING)
    retry_count = models.SmallIntegerField(default=0)
    max_retries = models.SmallIntegerField(default=10)
    available_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
