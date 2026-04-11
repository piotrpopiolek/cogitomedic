from __future__ import annotations

import json

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Q
from pydantic import ValidationError as PydanticValidationError

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
    from unfold.widgets import UnfoldAdminSelectWidget
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin
    UnfoldAdminSelectWidget = forms.Select

from apps.medical.api_schemas import FavoriteLesionGroupPreset
from apps.medical.constants import (
    CLINICAL_ASSESSMENT_CHOICES,
    DERMATOSCOPIC_FEATURE_CHOICES,
    MALIGNANCY_RISK_CHOICES,
)
from apps.core.translation_service import format_administration_message
from apps.medical.models import (
    DoctorTextTemplate,
    MedicalDocument,
    MedicalDocumentVersion,
)
from apps.medical.widgets import LesionGroupFavoritesWidget
from apps.users.models import StaffUserPreferredLocale

_ALLOWED_CLINICAL = {v for v, _ in CLINICAL_ASSESSMENT_CHOICES}
_ALLOWED_MALIGNANCY = {v for v, _ in MALIGNANCY_RISK_CHOICES}
_ALLOWED_FEATURES = {v for v, _ in DERMATOSCOPIC_FEATURE_CHOICES}


def _escape_curly_for_format(s: str) -> str:
    """Allow arbitrary text in str.format ``{details}`` without KeyError from braces."""
    return s.replace("{", "{{").replace("}", "}}")


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
        req = getattr(self, "_admin_request", None)
        value = self.cleaned_data.get("lesion_group_favorites")
        if value is None:
            return []
        if not isinstance(value, list):
            try:
                value = json.loads(value) if isinstance(value, str) else list(value)
            except (TypeError, ValueError):
                raise ValidationError(
                    format_administration_message(
                        "administration.error_lesion_favorites_invalid_json_list",
                        "Invalid JSON list for lesion group favorites.",
                        request=req,
                    )
                )
        for i, item in enumerate(value):
            preset_no = i + 1
            if not isinstance(item, dict):
                raise ValidationError(
                    format_administration_message(
                        "administration.error_lesion_favorites_preset_not_object",
                        "Preset {preset_no}: must be an object.",
                        request=req,
                        preset_no=preset_no,
                    )
                )
            try:
                FavoriteLesionGroupPreset.model_validate(item)
            except PydanticValidationError as e:
                errs = e.errors()
                msg = "; ".join(
                    f"{x.get('loc', [])}: {x.get('msg', '')}" for x in errs[:3]
                )
                raise ValidationError(
                    format_administration_message(
                        "administration.error_lesion_favorites_preset_invalid",
                        "Preset {preset_no}: {details}",
                        request=req,
                        preset_no=preset_no,
                        details=_escape_curly_for_format(msg),
                    )
                )
            for code in item.get("dermatoscopic_features") or []:
                if code not in _ALLOWED_FEATURES:
                    raise ValidationError(
                        format_administration_message(
                            "administration.error_lesion_favorites_preset_bad_feature",
                            "Preset {preset_no}: invalid dermatoscopic_features value '{code}'. Allowed: {allowed}.",
                            request=req,
                            preset_no=preset_no,
                            code=code,
                            allowed=", ".join(sorted(_ALLOWED_FEATURES)),
                        )
                    )
            ca = item.get("clinical_assessment")
            if ca and ca not in _ALLOWED_CLINICAL:
                raise ValidationError(
                    format_administration_message(
                        "administration.error_lesion_favorites_preset_bad_clinical",
                        "Preset {preset_no}: invalid clinical_assessment '{value}'. Allowed: {allowed}.",
                        request=req,
                        preset_no=preset_no,
                        value=ca,
                        allowed=", ".join(sorted(_ALLOWED_CLINICAL)),
                    )
                )
            mr = item.get("malignancy_risk")
            if mr and mr not in _ALLOWED_MALIGNANCY:
                raise ValidationError(
                    format_administration_message(
                        "administration.error_lesion_favorites_preset_bad_malignancy",
                        "Preset {preset_no}: invalid malignancy_risk '{value}'. Allowed: {allowed}.",
                        request=req,
                        preset_no=preset_no,
                        value=mr,
                        allowed=", ".join(sorted(_ALLOWED_MALIGNANCY)),
                    )
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
    list_display = (
        "queue_entry",
        "intake_form",
        "status",
        "current_version_no",
        "last_published_at",
        "created_by_user",
        "created_at",
    )
    list_display_links = ("queue_entry",)
    list_filter = ("status",)
    ordering = ["-created_at"]
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "locked_by_user",
        "locked_at",
    )
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "queue_entry",
            "queue_entry__patient",
            "intake_form",
            "created_by_user",
            "updated_by_user",
            "locked_by_user",
        )

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if (
            not change
            and request.user.is_authenticated
            and "created_by_user" in form.base_fields
        ):
            if form.base_fields["created_by_user"].initial is None:
                form.base_fields["created_by_user"].initial = request.user.pk
        return form

    def save_model(self, request, obj, form, change):
        _set_medical_document_users(request, obj, change)
        super().save_model(request, obj, form, change)


@admin.register(MedicalDocumentVersion)
class MedicalDocumentVersionAdmin(UnfoldModelAdmin):
    list_display = (
        "medical_document",
        "version_no",
        "version_status",
        "publish_locale",
        "pdf_generation_status",
        "diagnosis_code",
        "procedure_code",
        "created_at",
    )
    list_display_links = ("medical_document",)
    list_filter = ("version_status", "publish_locale", "pdf_generation_status")
    ordering = ["-created_at"]
    readonly_fields = ("id", "created_at")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "medical_document",
            "medical_document__queue_entry",
            "medical_document__queue_entry__patient",
            "medical_document__intake_form",
            "publish_requested_by_user",
            "published_by_user",
        )

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if "publish_locale" in form.base_fields:
            base = form.base_fields["publish_locale"]
            form.base_fields["publish_locale"] = forms.ChoiceField(
                choices=[("", "---------")] + list(StaffUserPreferredLocale.choices),
                required=base.required,
                label=base.label,
                help_text=base.help_text,
                initial=base.initial,
                widget=UnfoldAdminSelectWidget,
            )
        return form


@admin.register(DoctorTextTemplate)
class DoctorTextTemplateAdmin(UnfoldModelAdmin):
    form = DoctorTextTemplateForm
    list_display = (
        "name",
        "template_locale",
        "owner_user",
        "clinic_site",
        "updated_at",
        "created_at",
        "is_active",
    )
    list_display_links = ("name",)
    list_filter = ("template_locale", "is_active")
    ordering = ["-created_at"]
    search_fields = ("name", "template_body")
    raw_id_fields = ("owner_user", "clinic_site")
    readonly_fields = ("id", "created_at", "updated_at")

    def get_form(self, request, obj=None, change=None, **kwargs):
        form_class = super().get_form(request, obj, change, **kwargs)
        if "template_locale" in form_class.base_fields:
            base = form_class.base_fields["template_locale"]
            form_class.base_fields["template_locale"] = forms.ChoiceField(
                choices=StaffUserPreferredLocale.choices,
                required=base.required,
                label=base.label,
                help_text=base.help_text,
                initial=base.initial,
                widget=UnfoldAdminSelectWidget,
            )
        _req = request

        class DoctorTextTemplateFormWithRequest(form_class):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._admin_request = _req

        return DoctorTextTemplateFormWithRequest

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # DOCTOR: see own templates + clinic templates + global templates
        if request.user.is_doctor and not request.user.is_superuser:
            qs = qs.filter(
                Q(owner_user=request.user)
                | Q(clinic_site_id__in=request.user.clinic_sites.all())
                | Q(is_global=True)
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
