from __future__ import annotations

from django.contrib import admin

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin

from apps.operations.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(UnfoldModelAdmin):
    list_display = ("id", "event_time", "event_type", "actor_user", "patient", "medical_document", "outbox_event")
    list_filter = ("event_type",)
    raw_id_fields = ("actor_user", "patient", "medical_document", "outbox_event")
    readonly_fields = ("id", "event_time", "event_type", "actor_user", "patient", "medical_document", "outbox_event", "metadata")
    date_hierarchy = "event_time"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # DOCTOR: only see events where they are author OR assigned to queue (via metadata)
        if getattr(request.user, "role", None) == "DOCTOR" and not request.user.is_superuser:
            from django.db.models import Q
            qs = qs.filter(
                Q(metadata__assigned_doctor_id=str(request.user.id)) |
                Q(metadata__actor_user_id=str(request.user.id)) |
                Q(actor_user_id=request.user.id)
            )
        return qs
