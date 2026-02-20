from __future__ import annotations

from django.contrib import admin

from apps.medical.models import DoctorTextTemplate, MedicalDocument, MedicalDocumentVersion


@admin.register(MedicalDocument)
class MedicalDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "queue_entry", "intake_form", "status", "current_version_no", "last_published_at", "created_by_user", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("queue_entry", "intake_form", "created_by_user", "updated_by_user")
    readonly_fields = ("id", "created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(MedicalDocumentVersion)
class MedicalDocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "medical_document",
        "version_no",
        "version_status",
        "pdf_generation_status",
        "diagnosis_code",
        "procedure_code",
        "created_at",
    )
    list_filter = ("version_status", "pdf_generation_status")
    raw_id_fields = ("medical_document", "publish_requested_by_user", "published_by_user")
    readonly_fields = ("id", "created_at")
    date_hierarchy = "created_at"


@admin.register(DoctorTextTemplate)
class DoctorTextTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "template_locale", "owner_user", "is_global", "is_active", "created_at", "updated_at")
    list_filter = ("template_locale", "is_global", "is_active")
    search_fields = ("name", "template_body")
    raw_id_fields = ("owner_user",)
    readonly_fields = ("id", "created_at", "updated_at")
