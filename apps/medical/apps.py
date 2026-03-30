from django.apps import AppConfig

from apps.core.translation_service import db_gettext_lazy


class MedicalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.medical"
    verbose_name = db_gettext_lazy("administration.app_medical", "Medical")
