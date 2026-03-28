"""Middleware for core app."""
from __future__ import annotations

from apps.core.translation_service import get_current_request, set_current_request


class CsrfTrustTunnelOriginMiddleware:
    """
    Deprecated no-op middleware.

    Legacy implementation modified ``settings.CSRF_TRUSTED_ORIGINS`` at runtime.
    CSRF trusted origins are now configured statically via environment variable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
