"""Middleware for core app."""

from __future__ import annotations

from django.utils import translation

from apps.core.translation_service import set_current_request

_PREFERRED_LOCALE_TO_DJANGO_LANG: dict[str, str] = {
    "de-DE": "de",
    "en-GB": "en",
    "pl-PL": "pl",
}


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


class StaffLocaleMiddleware:
    """
    Activate the Django gettext language based on the authenticated staff user's
    ``preferred_locale`` (default: ``de-DE`` → ``de``).

    Must be placed **after** ``AuthenticationMiddleware`` in MIDDLEWARE so that
    ``request.user`` is already populated.  Overrides whatever language
    ``LocaleMiddleware`` picked from the browser's ``Accept-Language`` header,
    ensuring the admin UI renders in the staff-member's chosen language rather
    than the visitor's browser locale.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lang = self._resolve_lang(request)
        if lang:
            translation.activate(lang)
            request.LANGUAGE_CODE = lang
        response = self.get_response(request)
        translation.deactivate()
        return response

    @staticmethod
    def _resolve_lang(request) -> str | None:
        user = getattr(request, "user", None)
        if not (user and getattr(user, "is_authenticated", False)):
            return None
        preferred = getattr(user, "preferred_locale", None) or "de-DE"
        return _PREFERRED_LOCALE_TO_DJANGO_LANG.get(preferred, "de")


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
