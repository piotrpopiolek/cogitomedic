from __future__ import annotations

import contextvars
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils.functional import lazy

# Models imported lazily inside functions to avoid AppRegistryNotReady when this
# module is imported from other apps' models.py during Django startup.

ALLOWED_LANGUAGE_CODES = {"de-DE", "en-GB", "pl-PL"}
ADMINISTRATION_CATEGORY = "administration"

_current_request: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "translation_current_request", default=None
)


def set_current_request(request: Any) -> None:
    """Set the current request for the active context (called by middleware)."""
    _current_request.set(request)


def get_current_request() -> Any:
    """Return the current request if set by middleware, else None."""
    return _current_request.get(None)


def normalize_language_code(value: str) -> str:
    if not value:
        return "de-DE"
    low = value.lower()
    if low.startswith("en"):
        return "en-GB"
    if low.startswith("pl"):
        return "pl-PL"
    return "de-DE"


def _ensure_cache_version(category: str, language_code: str):
    from apps.core.models import TranslationCacheVersion

    normalized = normalize_language_code(language_code)
    obj, _ = TranslationCacheVersion.objects.get_or_create(
        category=category,
        language_code=normalized,
        defaults={"version": 1},
    )
    return obj


@transaction.atomic
def bump_translation_version(category: str, language_code: str) -> None:
    from apps.core.models import TranslationCacheVersion, TranslationCategory

    if category not in TranslationCategory.values:
        return
    normalized = _ensure_cache_version(category, language_code).language_code
    TranslationCacheVersion.objects.filter(
        category=category,
        language_code=normalized,
    ).update(version=F("version") + 1)


def get_translation_map(category: str, language_code: str) -> dict[str, str]:
    from apps.core.models import (
        TranslationCategory,
        TranslationKeyStatus,
        TranslationValue,
    )

    if category not in TranslationCategory.values:
        return {}
    version_obj = _ensure_cache_version(category, language_code)
    normalized = version_obj.language_code
    cache_key = f"i18n:data:{category}:{normalized}:v{version_obj.version}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    rows = TranslationValue.objects.select_related("translation_key").filter(
        translation_key__category=category,
        translation_key__status=TranslationKeyStatus.ACTIVE,
        language_code=normalized,
    )
    data = {row.translation_key.key: row.value for row in rows}
    cache.set(cache_key, data, timeout=300)
    return data


def _get_admin_map_for_request(request: Any) -> dict[str, str]:
    """Return administration translation map for request language; cache on request."""
    if not request:
        return get_translation_map(ADMINISTRATION_CATEGORY, "de-DE")
    cache_attr = "_admin_i18n_map"
    if getattr(request, cache_attr, None) is not None:
        return getattr(request, cache_attr)
    # Prefer authenticated user's preferred_locale so profile "Preferred locale" controls admin UI.
    if (
        getattr(request, "user", None)
        and getattr(request.user, "is_authenticated", False)
        and request.user.is_authenticated
    ):
        locale = getattr(request.user, "preferred_locale", None) or ""
        lang = normalize_language_code(locale)
    elif getattr(request, "LANGUAGE_CODE", None):
        lang = normalize_language_code(request.LANGUAGE_CODE)
    else:
        lang = "de-DE"
    data = get_translation_map(ADMINISTRATION_CATEGORY, lang)
    setattr(request, cache_attr, data)
    return data


def get_admin_translation(request: Any, key: str, default: str = "") -> str:
    """
    Return administration translation for the given request and key (full key e.g.
    administration.btn_save). Use in templates when request is in context.
    """
    if not request:
        return default
    mapping = _get_admin_map_for_request(request)
    return mapping.get(key, default)


def format_administration_message(
    key: str,
    default: str,
    request: Any | None = None,
    **params: Any,
) -> str:
    """
    Load an administration string from DB and apply ``str.format`` placeholders
    (e.g. ``{preset_no}``). Used for admin form validation messages where the
    template is stored in ``translation_data`` with allowed placeholders.
    """
    req = request if request is not None else get_current_request()
    if req:
        mapping = _get_admin_map_for_request(req)
    else:
        mapping = get_translation_map(ADMINISTRATION_CATEGORY, "de-DE")
    template = mapping.get(key, default)
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        try:
            return default.format(**params)
        except (KeyError, ValueError):
            return default


def _resolve_db_gettext(key: str, default: str) -> str:
    """Resolve a single admin translation key; used by db_gettext_lazy."""
    request = get_current_request()
    if not request:
        return default
    mapping = _get_admin_map_for_request(request)
    return mapping.get(key, default)


def db_gettext_lazy(key: str, default: str = "") -> Any:
    """
    Return a lazy proxy that resolves to the administration translation for the current
    request language when forced (e.g. in template). Requires middleware that sets the
    current request (TranslationRequestMiddleware).
    """
    return lazy(_resolve_db_gettext, str)(key, default)


def get_doctor_ui(lang: str) -> dict[str, str]:
    """Return doctor UI strings from DB-only translation storage."""
    normalized = normalize_language_code(lang)
    mapping = get_translation_map(category="doctor", language_code=normalized)
    ui: dict[str, str] = {}
    for full_key, value in mapping.items():
        if not full_key.startswith("doctor."):
            continue
        if full_key.startswith("doctor.fitzpatrick.") or full_key.startswith(
            "doctor.pdf_label."
        ):
            continue
        short_key = full_key.split(".", 1)[1]
        ui[short_key] = value
    return ui


def get_fitzpatrick_choices(lang: str) -> list[tuple[str, str]]:
    """Return (value, label) pairs for Fitzpatrick from DB-only translation storage."""
    normalized = normalize_language_code(lang)
    mapping = get_translation_map(category="doctor", language_code=normalized)
    codes = [
        "TYPE_I",
        "TYPE_II",
        "TYPE_III",
        "TYPE_IV",
        "TYPE_V",
        "TYPE_VI",
        "TYPE_II_III",
        "UNDETERMINED",
    ]
    choices: list[tuple[str, str]] = []
    for code in codes:
        key = f"doctor.fitzpatrick.{code}"
        label = mapping.get(key) or code.replace("_", " ").title()
        choices.append((code, label))
    return choices


def get_form_ui_strings(form_locale: str) -> dict[str, str]:
    """Return tablet form UI from DB-only translation storage."""
    lang = normalize_language_code(form_locale)
    mapping = get_translation_map(category="waiting_room", language_code=lang)
    ui: dict[str, str] = {}
    prefix = "waiting_room.form."
    for full_key, value in mapping.items():
        if full_key.startswith(prefix):
            ui[full_key[len(prefix) :]] = value
    return ui


def get_staff_ui_strings(locale: str) -> dict[str, str]:
    """Return tablet staff/waiting room UI from DB-only translation storage."""
    lang = normalize_language_code(locale)
    mapping = get_translation_map(category="waiting_room", language_code=lang)
    ui: dict[str, str] = {}
    prefix = "waiting_room.staff."
    for full_key, value in mapping.items():
        if full_key.startswith(prefix):
            ui[full_key[len(prefix) :]] = value
    return ui


def translation_category_for_message_key(key: str) -> str:
    """Map full translation key prefix to ``TranslationCategory`` value."""
    if key.startswith("administration."):
        return "administration"
    if key.startswith("doctor."):
        return "doctor"
    if key.startswith("waiting_room."):
        return "waiting_room"
    return "other"


def resolve_other_message(
    request: Any | None,
    key: str,
    default: str,
    **params: Any,
) -> str:
    """
    Resolve a message from DB using the key's category (``other``, ``doctor``, …) and
    active request language; apply ``str.format`` when *params* are provided.
    """
    from django.utils import translation

    lang: str | None = None
    if request is not None:
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False) and user.is_authenticated:
            loc = getattr(user, "preferred_locale", None) or ""
            if loc:
                lang = normalize_language_code(loc)
        if lang is None:
            lang = normalize_language_code(
                getattr(request, "LANGUAGE_CODE", None)
                or translation.get_language()
                or "de-DE"
            )
    else:
        lang = normalize_language_code(translation.get_language() or "de-DE")
    category = translation_category_for_message_key(key)
    data = get_translation_map(category, lang)
    template = data.get(key, default)
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        try:
            return default.format(**params)
        except (KeyError, ValueError):
            return default


def resolve_api_error_message(request: Any, key: str, default: str) -> str:
    """Resolve ``other.api.*`` (or any keyed message) from DB for *request*."""
    return resolve_other_message(request, key, default)


def get_ergebnisse_ui_strings(locale: str) -> dict[str, str]:
    """Return ergebnisse portal UI from DB-only translation storage."""
    lang = normalize_language_code(locale)
    mapping = get_translation_map(category="other", language_code=lang)
    ui: dict[str, str] = {}
    prefix = "other.ergebnisse."
    for full_key, value in mapping.items():
        if full_key.startswith(prefix):
            ui[full_key[len(prefix) :]] = value
    return ui
