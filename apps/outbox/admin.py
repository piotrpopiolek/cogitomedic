from __future__ import annotations

from django.contrib import admin

from apps.core.admin_list_page_size import CogitomedicaModelAdmin

from apps.outbox.models import OutboxEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(CogitomedicaModelAdmin):
    list_display = (
        "event_type",
        "status",
        "retry_count",
        "max_retries",
        "medical_document_version",
        "available_at",
        "processed_at",
        "created_at",
    )
    list_display_links = ("event_type",)
    list_filter = ("event_type", "status")
    ordering = ["-created_at"]
    search_fields = ("error_message",)
    readonly_fields = (
        "id",
        "aggregate_type",
        "aggregate_id",
        "payload",
        "payload_schema_version",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "medical_document_version",
            "medical_document_version__medical_document",
            "medical_document_version__medical_document__queue_entry",
            "medical_document_version__medical_document__queue_entry__patient",
            "medical_document_version__medical_document__intake_form",
        )
