from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import TranslationKey, TranslationKeyStatus, TranslationValue
from apps.core.translation_service import ALLOWED_LANGUAGE_CODES


class Command(BaseCommand):
    help = "Validate that each ACTIVE translation key has values for all required languages."

    def handle(self, *args: Any, **options: Any) -> None:
        missing: list[str] = []
        active_keys = TranslationKey.objects.filter(
            status=TranslationKeyStatus.ACTIVE
        ).order_by("key")
        active_count = active_keys.count()
        if active_count == 0:
            raise CommandError(
                "Translations completeness check failed: no ACTIVE translation keys found. "
                "Run load_default_translations first."
            )
        for key in active_keys:
            present = set(
                TranslationValue.objects.filter(translation_key=key).values_list(
                    "language_code", flat=True
                )
            )
            expected = set(ALLOWED_LANGUAGE_CODES)
            lacking = sorted(expected - present)
            if lacking:
                missing.append(f"{key.key}: missing {', '.join(lacking)}")
        if missing:
            msg = "Translations completeness check failed:\n" + "\n".join(missing)
            raise CommandError(msg)
        self.stdout.write(self.style.SUCCESS("Translations completeness check passed."))
