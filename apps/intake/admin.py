from __future__ import annotations

from django.contrib import admin
from django.urls import reverse

from apps.intake.models import (
    AnamnesisOptionDefinition,
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    PatientIntakeConsent,
    PatientIntakeForm,
)

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin


@admin.register(ConsentDefinition)
class ConsentDefinitionAdmin(UnfoldModelAdmin):
    show_add_link = True
    list_display = ("code", "version", "title_de", "title_en", "title_pl", "is_required", "display_order", "effective_from", "created_at", "is_active")
    list_display_links = ("code",)
    list_filter = ("is_required", "is_active")
    search_fields = ("code", "title_de", "title_en", "title_pl")
    ordering = ["-created_at"]
    fieldsets = (
        (None, {"fields": ("code", "version", "is_required", "is_active", "display_order", "effective_to")}),
        ("Deutsch", {"fields": ("title_de", "content_de")}),
        ("English", {"fields": ("title_en", "content_en")}),
        ("Polski", {"fields": ("title_pl", "content_pl")}),
    )

    def has_add_permission(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return True
        return super().has_add_permission(request)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        if self.has_add_permission(request):
            info = self.model._meta.app_label, self.model._meta.model_name
            extra_context["add_url"] = reverse("admin:%s_%s_add" % info)
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(AnamnesisQuestionDefinition)
class AnamnesisQuestionDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "version", "answer_type", "question_text_de", "question_text_pl", "is_required", "display_order", "created_at", "is_active")
    list_filter = ("answer_type", "is_required", "is_active")
    search_fields = ("code", "question_text_de", "question_text_en", "question_text_pl")
    ordering = ["-created_at"]


@admin.register(AnamnesisOptionDefinition)
class AnamnesisOptionDefinitionAdmin(admin.ModelAdmin):
    list_display = ("question", "code", "option_text_de", "option_text_pl", "display_order", "created_at", "is_active")
    list_display_links = ("question",)
    list_filter = ("is_active",)
    search_fields = ("code", "option_text_de", "option_text_en", "option_text_pl")
    raw_id_fields = ("question",)
    ordering = ["-created_at"]


@admin.register(PatientIntakeForm)
class PatientIntakeFormAdmin(admin.ModelAdmin):
    list_display = ("id", "queue_entry", "form_status", "submitted_at", "created_at", "updated_at")
    list_display_links = ("id",)
    list_filter = ("form_status",)
    ordering = ["-created_at"]
    raw_id_fields = ("queue_entry", "session")
    readonly_fields = ("id", "created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(PatientIntakeConsent)
class PatientIntakeConsentAdmin(admin.ModelAdmin):
    list_display = ("intake_form", "consent_definition", "accepted", "accepted_at")
    list_filter = ("accepted",)
    raw_id_fields = ("intake_form", "consent_definition")


@admin.register(IntakeDocumentVersion)
class IntakeDocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "intake_form",
        "version_no",
        "form_locale",
        "pdf_generation_status",
        "hidrive_sent",
        "created_at",
    )
    list_display_links = ("id",)
    list_filter = ("pdf_generation_status", "hidrive_sent", "form_locale")
    ordering = ["-created_at"]
    raw_id_fields = ("intake_form",)
    readonly_fields = (
        "id",
        "snapshot_payload",
        "pdf_checksum_sha256",
        "hidrive_path",
        "hidrive_sent_at",
        "created_at",
    )
    date_hierarchy = "created_at"


@admin.register(IntakeOutboxEvent)
class IntakeOutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "event_type",
        "status",
        "retry_count",
        "max_retries",
        "intake_document_version",
        "available_at",
        "processed_at",
        "created_at",
    )
    list_display_links = ("id",)
    list_filter = ("event_type", "status")
    ordering = ["-created_at"]
    search_fields = ("error_message",)
    raw_id_fields = ("intake_document_version",)
    readonly_fields = ("id", "aggregate_type", "aggregate_id", "payload", "payload_schema_version", "created_at", "updated_at")
    date_hierarchy = "created_at"
