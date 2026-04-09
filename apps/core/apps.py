from django.apps import AppConfig

from apps.core.translation_service import db_gettext_lazy


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = db_gettext_lazy("administration.app_core", "Core")

    def ready(self) -> None:
        from django.contrib import admin

        # Register model signal handlers.
        from apps.core import signals  # noqa: F401

        admin.site.index_title = db_gettext_lazy(
            "administration.admin_index_title",
            "Site administration",
        )
