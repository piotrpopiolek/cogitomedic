"""Middleware for core app."""
from __future__ import annotations

from apps.core.translation_service import get_current_request, set_current_request


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
