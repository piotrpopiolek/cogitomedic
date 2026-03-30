from django.apps import AppConfig

from apps.core.translation_service import db_gettext_lazy


class ReceptionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reception"
    verbose_name = db_gettext_lazy("administration.app_reception", "Reception")
