from __future__ import annotations

from django import forms
from django.contrib import admin

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
    from unfold.widgets import UnfoldAdminSelectWidget
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin
    UnfoldAdminSelectWidget = forms.Select

from apps.core.models import TranslationCacheVersion, TranslationKey, TranslationValue
from apps.users.models import StaffUserPreferredLocale


@admin.register(TranslationKey)
class TranslationKeyAdmin(UnfoldModelAdmin):
    list_display = ("key", "category", "status", "is_html_allowed", "updated_at")
    list_display_links = ("key",)
    list_filter = ("category", "status", "is_html_allowed")
    ordering = ["-created_at"]
    search_fields = ("key", "description")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(TranslationValue)
class TranslationValueAdmin(UnfoldModelAdmin):
    list_display = ("translation_key", "language_code", "value_preview", "updated_by", "updated_at")
    list_filter = ("language_code", "translation_key__category", "value")
    ordering = ["-created_at"]
    search_fields = ("translation_key__key", "value")
    raw_id_fields = ("translation_key", "updated_by")
    readonly_fields = ("id", "created_at", "updated_at")

    def get_form(self, request, obj=None, change=None, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if "language_code" in form.base_fields:
            base = form.base_fields["language_code"]
            form.base_fields["language_code"] = forms.ChoiceField(
                choices=StaffUserPreferredLocale.choices,
                required=base.required,
                label=base.label,
                help_text=base.help_text,
                initial=base.initial,
                widget=UnfoldAdminSelectWidget,
            )
        return form

    def save_model(self, request, obj, form, change):
        if request.user.is_authenticated:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Translation")
    def value_preview(self, obj: TranslationValue) -> str:
        value = (obj.value or "").strip()
        if len(value) <= 120:
            return value
        return f"{value[:117]}..."


@admin.register(TranslationCacheVersion)
class TranslationCacheVersionAdmin(UnfoldModelAdmin):
    list_display = ("category", "language_code", "version", "updated_at")
    list_display_links = ("category",)
    list_filter = ("category", "language_code")
    ordering = ["-created_at"]
    readonly_fields = ("id", "created_at", "updated_at")
