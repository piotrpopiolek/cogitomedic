from django.apps import AppConfig

from apps.core.translation_service import db_gettext_lazy


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = db_gettext_lazy("administration.app_core", "Core")

    def ready(self) -> None:
        from django.contrib import admin
        from django.shortcuts import redirect

        # Register model signal handlers.
        from apps.core import signals  # noqa: F401
        from apps.operations.accounting_access import is_accounting_only_staff

        admin.site.index_title = db_gettext_lazy(
            "administration.admin_index_title",
            "Site administration",
        )

        _original_index = admin.site.index

        def index(request, extra_context=None):
            if is_accounting_only_staff(request.user):
                return redirect("admin_accounting_report")
            return _original_index(request, extra_context=extra_context)

        admin.site.index = index
