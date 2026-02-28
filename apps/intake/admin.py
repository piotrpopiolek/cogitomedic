from __future__ import annotations

from django.contrib import admin

from apps.intake.models import (
    AnamnesisOptionDefinition,
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    IntakeDocumentVersion,
    IntakeOutboxEvent,
    PatientIntakeConsent,
    PatientIntakeForm,
)


@admin.register(ConsentDefinition)
class ConsentDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "version", "title_de", "title_en", "title_pl", "is_required", "is_active", "display_order", "effective_from", "created_at")
    list_filter = ("is_required", "is_active")
    search_fields = ("code", "title_de", "title_en", "title_pl")
    ordering = ("code", "version")
    fieldsets = (
        (None, {"fields": ("code", "version", "is_required", "is_active", "display_order", "effective_to")}),
        ("Deutsch", {"fields": ("title_de", "content_de")}),
        ("English", {"fields": ("title_en", "content_en")}),
        ("Polski", {"fields": ("title_pl", "content_pl")}),
    )


@admin.register(AnamnesisQuestionDefinition)
class AnamnesisQuestionDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "version", "answer_type", "question_text_de", "question_text_pl", "is_required", "is_active", "display_order", "created_at")
    list_filter = ("answer_type", "is_required", "is_active")
    search_fields = ("code", "question_text_de", "question_text_en", "question_text_pl")
    ordering = ("code", "version")


@admin.register(AnamnesisOptionDefinition)
class AnamnesisOptionDefinitionAdmin(admin.ModelAdmin):
    list_display = ("question", "code", "option_text_de", "option_text_pl", "display_order", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "option_text_de", "option_text_en", "option_text_pl")
    raw_id_fields = ("question",)


@admin.register(PatientIntakeForm)
class PatientIntakeFormAdmin(admin.ModelAdmin):
    list_display = ("id", "queue_entry", "form_status", "submitted_at", "created_at", "updated_at")
    list_filter = ("form_status",)
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
    list_filter = ("pdf_generation_status", "hidrive_sent", "form_locale")
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
    list_filter = ("event_type", "status")
    search_fields = ("error_message",)
    raw_id_fields = ("intake_document_version",)
    readonly_fields = ("id", "aggregate_type", "aggregate_id", "payload", "payload_schema_version", "created_at", "updated_at")
    date_hierarchy = "created_at"
