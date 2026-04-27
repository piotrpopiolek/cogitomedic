"""Middleware for core app."""

from __future__ import annotations

from django.conf import settings
from django.utils import translation

from apps.core.translation_service import normalize_language_code, set_current_request

_PREFERRED_LOCALE_TO_DJANGO_LANG: dict[str, str] = {
    "de-DE": "de",
    "en-GB": "en",
    "pl-PL": "pl",
}

_SESSION_EXPIRY_ROLES = (
    "is_doctor",
    "is_admin_role",
    "is_reception",
    "is_manager",
)


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


class RoleBasedSessionExpiryMiddleware:
    """
    Refresh session expiry for authenticated staff roles using per-role timeouts
    (doctor, admin, reception, manager, tablet).

    Global ``SESSION_COOKIE_AGE`` remains the fallback for anonymous or non-staff flows.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        session = getattr(request, "session", None)
        if user and getattr(user, "is_authenticated", False) and session is not None:
            expiry_seconds = self._resolve_expiry_seconds(user)
            if expiry_seconds is not None:
                session.set_expiry(expiry_seconds)
        return self.get_response(request)

    @staticmethod
    def _resolve_expiry_seconds(user) -> int | None:
        if getattr(user, "is_tablet", False):
            return int(getattr(settings, "TABLET_SESSION_COOKIE_AGE", 7 * 24 * 60 * 60))
        if any(getattr(user, role_attr, False) for role_attr in _SESSION_EXPIRY_ROLES):
            return int(getattr(settings, "STAFF_SESSION_COOKIE_AGE", 8 * 60 * 60))
        return None


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
        if lang:
            response["X-Staff-Lang"] = lang
        translation.deactivate()
        return response

    @staticmethod
    def _resolve_lang(request) -> str | None:
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            preferred = getattr(user, "preferred_locale", None) or "de-DE"
            normalized = normalize_language_code(preferred)
            return _PREFERRED_LOCALE_TO_DJANGO_LANG.get(normalized, "de")
        # Anonymous: honour ?language= param (persisted in session), default DE
        lang_param = (getattr(request, "GET", {}).get("language") or "").strip().lower()
        if lang_param in ("de", "en", "pl"):
            request.session["anon_language"] = lang_param
            return lang_param
        return request.session.get("anon_language", "de")


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
