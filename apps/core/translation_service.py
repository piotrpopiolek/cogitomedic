from __future__ import annotations

from django.core.cache import cache
from django.db import transaction
from django.db.models import F

from apps.core.models import (
    TranslationCacheVersion,
    TranslationCategory,
    TranslationKeyStatus,
    TranslationValue,
)

ALLOWED_LANGUAGE_CODES = {"de", "en", "pl"}


def normalize_language_code(value: str) -> str:
    if not value:
        return "de"
    low = value.lower()
    if low.startswith("en"):
        return "en"
    if low.startswith("pl"):
        return "pl"
    return "de"


def _ensure_cache_version(category: str, language_code: str) -> TranslationCacheVersion:
    normalized = normalize_language_code(language_code)
    obj, _ = TranslationCacheVersion.objects.get_or_create(
        category=category,
        language_code=normalized,
        defaults={"version": 1},
    )
    return obj


@transaction.atomic
def bump_translation_version(category: str, language_code: str) -> None:
    normalized = normalize_language_code(language_code)
    if category not in TranslationCategory.values:
        return
    _ensure_cache_version(category, normalized)
    TranslationCacheVersion.objects.filter(
        category=category,
        language_code=normalized,
    ).update(version=F("version") + 1)


def get_translation_map(category: str, language_code: str) -> dict[str, str]:
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
