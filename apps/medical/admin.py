from __future__ import annotations

import json

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Q
from pydantic import ValidationError as PydanticValidationError

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin

from apps.medical.api_schemas import FavoriteLesionGroupPreset
from apps.medical.constants import (
    CLINICAL_ASSESSMENT_CHOICES,
    DERMATOSCOPIC_FEATURE_CHOICES,
    MALIGNANCY_RISK_CHOICES,
)
from apps.medical.models import DoctorTextTemplate, MedicalDocument, MedicalDocumentVersion
from apps.medical.widgets import LesionGroupFavoritesWidget

_ALLOWED_CLINICAL = {v for v, _ in CLINICAL_ASSESSMENT_CHOICES}
_ALLOWED_MALIGNANCY = {v for v, _ in MALIGNANCY_RISK_CHOICES}
_ALLOWED_FEATURES = {v for v, _ in DERMATOSCOPIC_FEATURE_CHOICES}


class DoctorTextTemplateForm(forms.ModelForm):
    class Meta:
        model = DoctorTextTemplate
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lesion_group_favorites"].widget = LesionGroupFavoritesWidget()
        self.fields["lesion_group_favorites"].help_text = (
            "With JavaScript enabled, a visual editor is available. You can also edit the JSON directly."
        )

    def clean_lesion_group_favorites(self):
        value = self.cleaned_data.get("lesion_group_favorites")
        if value is None:
            return []
        if not isinstance(value, list):
            try:
                value = json.loads(value) if isinstance(value, str) else list(value)
            except (TypeError, ValueError):
                raise ValidationError("Invalid JSON list.")
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                raise ValidationError(f"Preset {i + 1}: must be an object.")
            try:
                FavoriteLesionGroupPreset.model_validate(item)
            except PydanticValidationError as e:
                errs = e.errors()
                msg = "; ".join(f"{x.get('loc', [])}: {x.get('msg', '')}" for x in errs[:3])
                raise ValidationError(f"Preset {i + 1}: {msg}")
            for code in item.get("dermatoscopic_features") or []:
                if code not in _ALLOWED_FEATURES:
                    raise ValidationError(
                        f"Preset {i + 1}: invalid dermatoscopic_features value '{code}'. "
                        f"Allowed: {', '.join(sorted(_ALLOWED_FEATURES))}."
                    )
            ca = item.get("clinical_assessment")
            if ca and ca not in _ALLOWED_CLINICAL:
                raise ValidationError(
                    f"Preset {i + 1}: invalid clinical_assessment '{ca}'. "
                    f"Allowed: {', '.join(sorted(_ALLOWED_CLINICAL))}."
                )
            mr = item.get("malignancy_risk")
            if mr and mr not in _ALLOWED_MALIGNANCY:
                raise ValidationError(
                    f"Preset {i + 1}: invalid malignancy_risk '{mr}'. "
                    f"Allowed: {', '.join(sorted(_ALLOWED_MALIGNANCY))}."
                )
        return value


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
class MedicalDocumentAdmin(UnfoldModelAdmin):
    list_display = ("id", "queue_entry", "intake_form", "status", "current_version_no", "last_published_at", "created_by_user", "created_at")
    list_filter = ("status",)
    ordering = ["-created_at"]
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
class MedicalDocumentVersionAdmin(UnfoldModelAdmin):
    list_display = (
        "id",
        "medical_document",
        "version_no",
        "version_status",
        "publish_locale",
        "pdf_generation_status",
        "diagnosis_code",
        "procedure_code",
        "created_at",
    )
    list_filter = ("version_status", "publish_locale", "pdf_generation_status")
    ordering = ["-created_at"]
    raw_id_fields = ("medical_document", "publish_requested_by_user", "published_by_user")
    readonly_fields = ("id", "created_at")
    date_hierarchy = "created_at"


@admin.register(DoctorTextTemplate)
class DoctorTextTemplateAdmin(UnfoldModelAdmin):
    form = DoctorTextTemplateForm
    list_display = ("name", "template_locale", "owner_user", "clinic_site", "is_global", "is_active", "created_at", "updated_at")
    list_filter = ("template_locale", "is_global", "is_active")
    ordering = ["-created_at"]
    search_fields = ("name", "template_body")
    raw_id_fields = ("owner_user", "clinic_site")
    readonly_fields = ("id", "created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # DOCTOR: see own templates + clinic templates + global templates
        if request.user.is_doctor and not request.user.is_superuser:
            qs = qs.filter(
                Q(owner_user=request.user) |
                Q(clinic_site_id__in=request.user.clinic_sites.all()) |
                Q(is_global=True)
            ).distinct()
        return qs

    def has_change_permission(self, request, obj=None):
        # DOCTOR: can only edit own templates
        if request.user.is_doctor and not request.user.is_superuser:
            if obj is None:
                return True  # Allow viewing the list
            return obj.owner_user_id == request.user.id
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # DOCTOR: can only delete own templates
        if request.user.is_doctor and not request.user.is_superuser:
            if obj is None:
                return True  # Allow viewing the list
            return obj.owner_user_id == request.user.id
        return super().has_delete_permission(request, obj)

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
