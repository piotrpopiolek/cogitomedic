from __future__ import annotations

from django.contrib import admin

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin

from apps.core.models import TranslationCacheVersion, TranslationKey, TranslationValue


@admin.register(TranslationKey)
class TranslationKeyAdmin(UnfoldModelAdmin):
    list_display = ("key", "category", "status", "is_html_allowed", "updated_at")
    list_filter = ("category", "status", "is_html_allowed")
    search_fields = ("key", "description")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(TranslationValue)
class TranslationValueAdmin(UnfoldModelAdmin):
    list_display = ("translation_key", "language_code", "updated_by", "updated_at")
    list_filter = ("language_code", "translation_key__category")
    search_fields = ("translation_key__key", "value")
    raw_id_fields = ("translation_key", "updated_by")
    readonly_fields = ("id", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if request.user.is_authenticated:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TranslationCacheVersion)
class TranslationCacheVersionAdmin(UnfoldModelAdmin):
    list_display = ("category", "language_code", "version", "updated_at")
    list_filter = ("category", "language_code")
    readonly_fields = ("id", "created_at", "updated_at")
