"""Middleware for core app."""
from __future__ import annotations

from django.conf import settings

from apps.core.translation_service import get_current_request, set_current_request


class CsrfTrustTunnelOriginMiddleware:
    """
    Add request origin to CSRF_TRUSTED_ORIGINS when Host is from trycloudflare.com
    (quick tunnel URL changes each run). Must run before CsrfViewMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0]
        if host.endswith(".trycloudflare.com"):
            origin = f"https://{host}"
            if origin not in settings.CSRF_TRUSTED_ORIGINS:
                settings.CSRF_TRUSTED_ORIGINS = list(settings.CSRF_TRUSTED_ORIGINS) + [origin]
        return self.get_response(request)


class TranslationRequestMiddleware:
    """
    Set the current request in a contextvar so db_gettext_lazy can resolve
    administration translations for the request language.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            return self.get_response(request)
        finally:
            set_current_request(None)
