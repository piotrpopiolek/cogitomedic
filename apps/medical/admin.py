from __future__ import annotations

from django.contrib import admin

from apps.medical.models import DoctorTextTemplate, MedicalDocument, MedicalDocumentVersion


def _set_medical_document_users(request, obj, change: bool) -> None:
    """Set created_by_user / updated_by_user to session user in admin."""
    if not request.user.is_authenticated:
        return
    if not change:
        if getattr(obj, "created_by_user_id", None) is None:
            obj.created_by_user = request.user
        if getattr(obj, "updated_by_user_id", None) is None:
            obj.updated_by_user = request.user
    else:
        obj.updated_by_user = request.user


@admin.register(MedicalDocument)
class MedicalDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "queue_entry", "intake_form", "status", "current_version_no", "last_published_at", "created_by_user", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("queue_entry", "intake_form", "created_by_user", "updated_by_user")
    readonly_fields = ("id", "created_at", "updated_at")
    date_hierarchy = "created_at"

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if not change and request.user.is_authenticated and "created_by_user" in form.base_fields:
            if form.base_fields["created_by_user"].initial is None:
                form.base_fields["created_by_user"].initial = request.user.pk
        return form

    def save_model(self, request, obj, form, change):
        _set_medical_document_users(request, obj, change)
        super().save_model(request, obj, form, change)


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

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if request.user.is_authenticated:
            initial.setdefault("owner_user", request.user.pk)
        return initial

    def save_model(self, request, obj, form, change):
        # Keep DB constraint consistent in admin UX:
        # - global template must not have owner_user
        # - private template must have owner_user (default to current user)
        if obj.is_global:
            obj.owner_user = None
        elif obj.owner_user_id is None and request.user.is_authenticated:
            obj.owner_user = request.user
        super().save_model(request, obj, form, change)
