from __future__ import annotations

from django.contrib import admin

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin

from apps.outbox.models import OutboxEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(UnfoldModelAdmin):
    list_display = (
        "id",
        "event_type",
        "status",
        "retry_count",
        "max_retries",
        "medical_document_version",
        "available_at",
        "processed_at",
        "created_at",
    )
    list_filter = ("event_type", "status")
    ordering = ["-created_at"]
    search_fields = ("error_message",)
    raw_id_fields = ("medical_document_version",)
    readonly_fields = ("id", "aggregate_type", "aggregate_id", "payload", "payload_schema_version", "created_at", "updated_at")
    date_hierarchy = "created_at"
