from __future__ import annotations

import contextvars
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils.functional import lazy

# Models imported lazily inside functions to avoid AppRegistryNotReady when this
# module is imported from other apps' models.py during Django startup.

ALLOWED_LANGUAGE_CODES = {"de", "en", "pl"}
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
        return "de"
    low = value.lower()
    if low.startswith("en"):
        return "en"
    if low.startswith("pl"):
        return "pl"
    return "de"


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

    normalized = normalize_language_code(language_code)
    if category not in TranslationCategory.values:
        return
    _ensure_cache_version(category, normalized)
    TranslationCacheVersion.objects.filter(
        category=category,
        language_code=normalized,
    ).update(version=F("version") + 1)


def get_translation_map(category: str, language_code: str) -> dict[str, str]:
    from apps.core.models import TranslationCategory, TranslationKeyStatus, TranslationValue

    normalized = normalize_language_code(language_code)
    if category not in TranslationCategory.values:
        return {}
    version_obj = _ensure_cache_version(category, normalized)
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
        return get_translation_map(ADMINISTRATION_CATEGORY, "de")
    cache_attr = "_admin_i18n_map"
    if getattr(request, cache_attr, None) is not None:
        return getattr(request, cache_attr)
    # Prefer authenticated user's preferred_locale so profile "Preferred locale" controls admin UI.
    if getattr(request, "user", None) and getattr(request.user, "is_authenticated", False) and request.user.is_authenticated:
        locale = getattr(request.user, "preferred_locale", None) or ""
        lang = normalize_language_code(locale)
    elif getattr(request, "LANGUAGE_CODE", None):
        lang = normalize_language_code(request.LANGUAGE_CODE)
    else:
        lang = "de"
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
