from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.models import TranslationKey, TranslationValue
from apps.core.translation_service import (
    ALLOWED_LANGUAGE_CODES,
    bump_translation_version,
)


@receiver(post_save, sender=TranslationValue)
def _bump_translation_value_version_on_save(
    sender, instance: TranslationValue, **kwargs
):
    bump_translation_version(instance.translation_key.category, instance.language_code)


@receiver(post_delete, sender=TranslationValue)
def _bump_translation_value_version_on_delete(
    sender, instance: TranslationValue, **kwargs
):
    bump_translation_version(instance.translation_key.category, instance.language_code)


@receiver(post_save, sender=TranslationKey)
def _bump_translation_key_version_on_save(sender, instance: TranslationKey, **kwargs):
    for lang in ALLOWED_LANGUAGE_CODES:
        bump_translation_version(instance.category, lang)


@receiver(post_delete, sender=TranslationKey)
def _bump_translation_key_version_on_delete(sender, instance: TranslationKey, **kwargs):
    for lang in ALLOWED_LANGUAGE_CODES:
        bump_translation_version(instance.category, lang)
