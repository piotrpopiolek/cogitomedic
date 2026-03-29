"""Callbacks dla Unfold admin (dashboard, etykieta środowiska)."""

from django.conf import settings


def environment_callback(request):
    """Etykieta środowiska w headerze admina."""
    env = getattr(settings, "ENVIRONMENT", "dev")
    if env == "prod":
        return ["Production", "danger"]
    if env == "staging":
        return ["Staging", "warning"]
    return ["Development", "info"]


def dashboard_callback(request, context):
    """Dodatkowe zmienne do szablonu dashboardu admina."""
    return context
