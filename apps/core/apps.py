from django.apps import AppConfig

from apps.core.translation_service import db_gettext_lazy


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = db_gettext_lazy("administration.app_core", "Core")

    def ready(self) -> None:
        # Register model signal handlers.
        from apps.core import signals  # noqa: F401
