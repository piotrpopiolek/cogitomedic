"""
Template tags for DB-backed translations and consent Markdown rendering.

Usage in templates::

    {% load cogitomedica_i18n %}
    {% admin_trans "administration.btn_filter" "Filter" %}
    {{ consent.content|markdown_consent }}
"""

from __future__ import annotations

import re

import bleach
import markdown as md
from django import template
from django.utils.safestring import mark_safe

from apps.core.translation_service import (
    get_admin_translation,
    get_current_request,
    resolve_other_message,
)

register = template.Library()

_CONSENT_ALLOWED_TAGS = [
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "br",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
]
_CONSENT_ALLOWED_ATTRS = {"p": ["class"]}
_CENTER_RE = re.compile(r"^->\s*(.+?)\s*<-$", re.MULTILINE)


@register.simple_tag
def admin_trans(key: str, default: str = "") -> str:
    """Return the DB-backed administration translation for *key*.

    Falls back to *default* when the key is not found or the DB is unavailable.
    Uses the request stored in the contextvar by ``TranslationRequestMiddleware``
    so no extra context needs to be passed from views.
    """
    request = get_current_request()
    return get_admin_translation(request, key, default)


@register.simple_tag
def db_trans(key: str, default: str = "") -> str:
    """Return DB-backed translation for any key prefix category.

    Works with keys like ``administration.*``, ``doctor.*``, ``waiting_room.*``,
    and ``other.*``.
    """
    request = get_current_request()
    return resolve_other_message(request, key, default)


@register.simple_tag
def db_transf(key: str, default: str = "", **params: object) -> str:
    """DB-backed translation with ``str.format`` params support."""
    request = get_current_request()
    return resolve_other_message(request, key, default, **params)


@register.filter(name="markdown_consent")
def markdown_consent(value: str) -> str:
    """Convert Markdown to sanitised HTML for consent text display.

    Supports headings (``## Title``), **bold**, *italic*, lists,
    centered text (``-> text <-``), and automatic ``<br>`` for single
    newlines (``nl2br`` extension).
    Output is whitelist-sanitised via ``bleach`` to prevent XSS.
    """
    text = value or ""
    text = _CENTER_RE.sub(r'<p class="text-center">\1</p>', text)
    html = md.markdown(text, extensions=["nl2br"])
    safe_html = bleach.clean(
        html, tags=_CONSENT_ALLOWED_TAGS, attributes=_CONSENT_ALLOWED_ATTRS, strip=True
    )
    return mark_safe(safe_html)
