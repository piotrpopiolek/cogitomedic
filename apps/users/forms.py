from __future__ import annotations

from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import ValidationError

from apps.core.translation_service import db_gettext_lazy
from apps.users.models import StaffUser

try:
    from unfold.forms import UserCreationForm as BaseUserCreationForm
except ImportError:
    from django.contrib.auth.forms import AdminUserCreationForm as BaseUserCreationForm


def _validate_groups_not_empty(groups) -> None:
    if not groups:
        raise ValidationError(
            db_gettext_lazy(
                "administration.error_at_least_one_group", "Select at least one group."
            )
        )


class StaffUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = StaffUser

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if "groups" in self.fields:
            self.fields["groups"].required = True
            self.fields["groups"].label = db_gettext_lazy(
                "administration.field_groups", "Groups"
            )

    def clean_groups(self):
        groups = self.cleaned_data.get("groups")
        _validate_groups_not_empty(groups)
        return groups


class StaffUserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = StaffUser
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "preferred_locale",
            "is_staff",
            "is_active",
            "groups",
        )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if "groups" in self.fields:
            self.fields["groups"].required = True
            self.fields["groups"].label = db_gettext_lazy(
                "administration.field_groups", "Groups"
            )

    def clean_groups(self):
        groups = self.cleaned_data.get("groups")
        _validate_groups_not_empty(groups)
        return groups
