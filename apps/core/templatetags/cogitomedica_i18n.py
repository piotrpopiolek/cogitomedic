"""
Template tags for DB-backed translations.

Usage in templates::

    {% load cogitomedica_i18n %}
    {% admin_trans "administration.btn_filter" "Filter" %}
"""

from __future__ import annotations

from django import template

from apps.core.translation_service import get_admin_translation, get_current_request

register = template.Library()


@register.simple_tag
def admin_trans(key: str, default: str = "") -> str:
    """Return the DB-backed administration translation for *key*.

    Falls back to *default* when the key is not found or the DB is unavailable.
    Uses the request stored in the contextvar by ``TranslationRequestMiddleware``
    so no extra context needs to be passed from views.
    """
    request = get_current_request()
    return get_admin_translation(request, key, default)
