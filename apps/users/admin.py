from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils import timezone as django_timezone

from apps.core.admin_list_page_size import CogitomedicaModelAdmin

from apps.core.translation_service import db_gettext_lazy
from apps.users.api_views import get_primary_role
from apps.users.forms import StaffUserChangeForm, StaffUserCreationForm
from apps.users.models import ROLE_GROUP_NAME_MAP, StaffUser, VALID_STAFF_ROLES


@admin.register(StaffUser)
class StaffUserAdmin(CogitomedicaModelAdmin, BaseUserAdmin):
    form = StaffUserChangeForm
    add_form = StaffUserCreationForm
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "primary_role",
        "is_staff",
        "is_active",
        "last_login_display",
    )
    list_display_links = ("username",)
    list_filter = ("groups", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ["-created_at"]
    filter_horizontal = ("groups", "user_permissions", "clinic_sites")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Personal",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "phone_number",
                    "professional_title",
                    "gender",
                )
            },
        ),
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
                "fields": (
                    "username",
                    "email",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
        (
            "Personal",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "phone_number",
                    "professional_title",
                    "gender",
                )
            },
        ),
        ("Access", {"fields": ("preferred_locale", "is_staff", "is_active")}),
        ("Permissions", {"fields": ("groups",)}),
    )
    readonly_fields = ("date_joined", "last_login", "created_at", "updated_at")

    @staticmethod
    def _is_admin_role(request) -> bool:
        return request.user.is_authenticated and getattr(
            request.user, "is_admin_role", False
        )

    @staticmethod
    def _is_manager_role(request) -> bool:
        return request.user.is_authenticated and getattr(
            request.user, "is_manager", False
        )

    def has_module_permission(self, request):
        if self._is_manager_role(request):
            return False
        if self._is_admin_role(request):
            return True
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        if self._is_manager_role(request):
            return False
        if self._is_admin_role(request):
            return True
        return super().has_view_permission(request, obj=obj)

    def has_change_permission(self, request, obj=None):
        if self._is_manager_role(request):
            return False
        if self._is_admin_role(request):
            return True
        return super().has_change_permission(request, obj=obj)

    def has_add_permission(self, request):
        if self._is_manager_role(request):
            return False
        if self._is_admin_role(request):
            return True
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        if self._is_manager_role(request):
            return False
        if self._is_admin_role(request):
            return True
        return super().has_delete_permission(request, obj=obj)

    @admin.display(description="Rola")
    def primary_role(self, obj: StaffUser) -> str:
        if obj.is_superuser:
            return "SUPERUSER"
        role = get_primary_role(obj)
        return role if role else "—"

    @admin.display(
        description=db_gettext_lazy("administration.col_last_login", "Last login"),
        ordering="last_login",
    )
    def last_login_display(self, obj: StaffUser) -> str:
        if obj.last_login is None:
            return "—"
        return django_timezone.localtime(obj.last_login).strftime("%d.%m.%Y %H:%M")

    def get_queryset(self, request):
        qs = super().get_queryset(request).prefetch_related("groups")
        role = (request.GET.get("role") or "").upper()
        if role in VALID_STAFF_ROLES:
            qs = qs.filter(groups__name=ROLE_GROUP_NAME_MAP[role]).distinct()
        return qs

    def save_model(self, request, obj, form, change):
        # Admin-like roles must always be staff to access Django/Unfold admin.
        if getattr(obj, "is_admin_role", False) or getattr(obj, "is_manager", False):
            obj.is_staff = True
        super().save_model(request, obj, form, change)


class GroupAdmin(CogitomedicaModelAdmin, DjangoGroupAdmin):
    """auth.Group with the same changelist page-size switcher as other admin modules."""


try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass
admin.site.register(Group, GroupAdmin)
