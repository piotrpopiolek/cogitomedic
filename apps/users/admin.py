from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
except ImportError:
    UnfoldModelAdmin = admin.ModelAdmin

from apps.users.forms import StaffUserChangeForm, StaffUserCreationForm
from apps.users.models import StaffUser


@admin.register(StaffUser)
class StaffUserAdmin(UnfoldModelAdmin, BaseUserAdmin):
    form = StaffUserChangeForm
    add_form = StaffUserCreationForm
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
    )
    list_display_links = ("username",)
    list_filter = ("groups", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ["-created_at"]
    filter_horizontal = ("groups", "user_permissions", "clinic_sites")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "email", "phone_number")}),
        ("Access", {"fields": ("preferred_locale", "is_staff", "is_active")}),
        (
            "Kliniki (dla roli Lekarz)",
            {
                "fields": ("clinic_sites",),
                "description": "Z jakich placówek lekarz widzi pacjentów i kolejki.",
            },
        ),
        (
            "Dates",
            {"fields": ("date_joined", "last_login", "created_at", "updated_at")},
        ),
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
        ("Access", {"fields": ("preferred_locale", "is_staff", "is_active")}),
        ("Permissions", {"fields": ("groups",)}),
    )
    readonly_fields = ("date_joined", "last_login", "created_at", "updated_at")

    @staticmethod
    def _is_admin_role(request) -> bool:
        return request.user.is_authenticated and getattr(
            request.user, "is_admin_role", False
        )

    def has_view_permission(self, request, obj=None):
        if self._is_admin_role(request):
            return True
        return super().has_view_permission(request, obj=obj)

    def has_change_permission(self, request, obj=None):
        if self._is_admin_role(request):
            return True
        return super().has_change_permission(request, obj=obj)

    def has_add_permission(self, request):
        if self._is_admin_role(request):
            return True
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if self._is_admin_role(request):
            return True
        return super().has_delete_permission(request, obj=obj)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        role = (request.GET.get("role") or "").upper()
        if role in {"RECEPTION", "DOCTOR", "ADMIN", "TABLET"}:
            qs = qs.filter(groups__name=role.capitalize()).distinct()
        return qs

    def save_model(self, request, obj, form, change):
        # ADMIN role must always be staff to access Django/Unfold admin.
        if getattr(obj, "is_admin_role", False):
            obj.is_staff = True
        super().save_model(request, obj, form, change)
