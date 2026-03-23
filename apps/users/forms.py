from __future__ import annotations

from apps.users.models import StaffUser

try:
    from unfold.forms import UserCreationForm as BaseUserCreationForm
except ImportError:
    from django.contrib.auth.forms import AdminUserCreationForm as BaseUserCreationForm


class StaffUserCreationForm(BaseUserCreationForm):
    class Meta:
        model = StaffUser
        fields = ("username",)
