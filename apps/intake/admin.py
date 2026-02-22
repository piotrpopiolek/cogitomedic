from __future__ import annotations

from django.contrib import admin

from apps.intake.models import (
    AnamnesisOptionDefinition,
    AnamnesisQuestionDefinition,
    ConsentDefinition,
    PatientIntakeConsent,
    PatientIntakeForm,
)


@admin.register(ConsentDefinition)
class ConsentDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "version", "title_de", "title_en", "is_required", "is_active", "display_order", "effective_from", "created_at")
    list_filter = ("is_required", "is_active")
    search_fields = ("code", "title_de", "title_en")
    ordering = ("code", "version")
    fieldsets = (
        (None, {"fields": ("code", "version", "is_required", "is_active", "display_order", "effective_to")}),
        ("Deutsch", {"fields": ("title_de", "content_de")}),
        ("English", {"fields": ("title_en", "content_en")}),
    )


@admin.register(AnamnesisQuestionDefinition)
class AnamnesisQuestionDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "version", "answer_type", "question_text_de", "is_required", "is_active", "display_order", "created_at")
    list_filter = ("answer_type", "is_required", "is_active")
    search_fields = ("code", "question_text_de", "question_text_en")
    ordering = ("code", "version")


@admin.register(AnamnesisOptionDefinition)
class AnamnesisOptionDefinitionAdmin(admin.ModelAdmin):
    list_display = ("question", "code", "option_text_de", "display_order", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "option_text_de", "option_text_en")
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
