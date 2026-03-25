from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MedicalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.medical"
    verbose_name = _("Medical")
