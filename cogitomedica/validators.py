import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

class CustomPasswordValidator:
    def validate(self, password, user=None):
        if not re.findall('[A-Z]', password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jedną wielką literę."),
                code='password_no_upper',
            )
        if not re.findall('[a-z]', password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jedną małą literę."),
                code='password_no_lower',
            )
        if not re.findall('\d', password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jedną cyfrę."),
                code='password_no_digit',
            )
        if not re.findall('[^A-Za-z0-9]', password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jeden znak specjalny."),
                code='password_no_special',
            )

    def get_help_text(self):
        return _(
            "Hasło musi zawierać co najmniej jedną wielką literę, jedną małą literę, jedną cyfrę oraz jeden znak specjalny."
        )