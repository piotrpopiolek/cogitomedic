from __future__ import annotations

from django.contrib import admin

from apps.operations.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_time", "event_type", "actor_user", "patient", "medical_document", "outbox_event")
    list_filter = ("event_type",)
    raw_id_fields = ("actor_user", "patient", "medical_document", "outbox_event")
    readonly_fields = ("id", "event_time", "event_type", "actor_user", "patient", "medical_document", "outbox_event", "metadata")
    date_hierarchy = "event_time"
