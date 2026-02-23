from __future__ import annotations

from django.contrib.auth.backends import ModelBackend


class StaffRoleAdminBackend(ModelBackend):
    """Grant full Django permissions to staff users with role ADMIN."""

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj.is_active:
            return False
        if getattr(user_obj, "role", None) == "ADMIN":
            return True
        return super().has_perm(user_obj, perm, obj=obj)

    def has_module_perms(self, user_obj, app_label):
        if not user_obj.is_active:
            return False
        if getattr(user_obj, "role", None) == "ADMIN":
            return True
        return super().has_module_perms(user_obj, app_label)
