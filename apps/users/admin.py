from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.models import StaffUser


@admin.register(StaffUser)
class StaffUserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "email", "phone_number")}),
        ("Role & access", {"fields": ("role", "preferred_locale", "is_staff", "is_active")}),
        ("Dates", {"fields": ("date_joined", "last_login", "created_at", "updated_at")}),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
        ("Personal", {"fields": ("first_name", "last_name", "phone_number")}),
        ("Role & access", {"fields": ("role", "preferred_locale", "is_staff", "is_active")}),
    )
    readonly_fields = ("date_joined", "last_login", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        # ADMIN role must always be staff to access Django/Unfold admin.
        if getattr(obj, "role", None) == "ADMIN":
            obj.is_staff = True
        super().save_model(request, obj, form, change)
