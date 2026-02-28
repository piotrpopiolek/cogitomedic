from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import TranslationCategory, TranslationKey, TranslationKeyStatus, TranslationValue
from apps.medical.pdf_builder import PDF_LABELS
from cogitomedica.doctor_i18n import (
    DOCTOR_UI_DE,
    DOCTOR_UI_EN,
    DOCTOR_UI_PL,
    FITZPATRICK_DE,
    FITZPATRICK_EN,
    FITZPATRICK_PL,
)
from cogitomedica.tablet_i18n import (
    FORM_UI_DE,
    FORM_UI_EN,
    FORM_UI_PL,
    STAFF_UI_DE,
    STAFF_UI_EN,
    STAFF_UI_PL,
)


class Command(BaseCommand):
    help = "Seed DB-only translation tables with current default values."

    @staticmethod
    def _ensure_key(
        full_key: str,
        *,
        category: str,
        description: str = "",
    ) -> TranslationKey:
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": category,
                "description": description,
                "is_html_allowed": False,
                "allowed_placeholders": [],
                "status": TranslationKeyStatus.ACTIVE,
            },
        )
        return key

    @transaction.atomic
    def handle(self, *args, **options):
        created_values = 0
        source_ui = {"de": DOCTOR_UI_DE, "en": DOCTOR_UI_EN, "pl": DOCTOR_UI_PL}
        for lang, mapping in source_ui.items():
            for short_key, text in mapping.items():
                full_key = f"doctor.{short_key}"
                key = self._ensure_key(
                    full_key,
                    category=TranslationCategory.DOCTOR,
                    description="Doctor UI translation",
                )
                obj, created = TranslationValue.objects.get_or_create(
                    translation_key=key,
                    language_code=lang,
                    defaults={"value": text},
                )
                if created:
                    created_values += 1

        source_fitz = {"de": FITZPATRICK_DE, "en": FITZPATRICK_EN, "pl": FITZPATRICK_PL}
        for lang, rows in source_fitz.items():
            for code, text in rows:
                full_key = f"doctor.fitzpatrick.{code}"
                key = self._ensure_key(
                    full_key,
                    category=TranslationCategory.DOCTOR,
                    description="Fitzpatrick label",
                )
                obj, created = TranslationValue.objects.get_or_create(
                    translation_key=key,
                    language_code=lang,
                    defaults={"value": text},
                )
                if created:
                    created_values += 1

        locale_to_lang = {"de-DE": "de", "en-GB": "en", "pl-PL": "pl"}
        for locale, labels in PDF_LABELS.items():
            lang = locale_to_lang.get(locale)
            if not lang:
                continue
            for label_key, text in labels.items():
                full_key = f"doctor.pdf_label.{label_key}"
                key = self._ensure_key(
                    full_key,
                    category=TranslationCategory.DOCTOR,
                    description="Doctor PDF label",
                )
                obj, created = TranslationValue.objects.get_or_create(
                    translation_key=key,
                    language_code=lang,
                    defaults={"value": text},
                )
                if created:
                    created_values += 1

        form_ui_source = {"de": FORM_UI_DE, "en": FORM_UI_EN, "pl": FORM_UI_PL}
        for lang, mapping in form_ui_source.items():
            for short_key, text in mapping.items():
                full_key = f"waiting_room.form.{short_key}"
                key = self._ensure_key(
                    full_key,
                    category=TranslationCategory.WAITING_ROOM,
                    description="Waiting room tablet form UI",
                )
                obj, created = TranslationValue.objects.get_or_create(
                    translation_key=key,
                    language_code=lang,
                    defaults={"value": text},
                )
                if created:
                    created_values += 1

        staff_ui_source = {"de": STAFF_UI_DE, "en": STAFF_UI_EN, "pl": STAFF_UI_PL}
        for lang, mapping in staff_ui_source.items():
            for short_key, text in mapping.items():
                full_key = f"waiting_room.staff.{short_key}"
                key = self._ensure_key(
                    full_key,
                    category=TranslationCategory.WAITING_ROOM,
                    description="Waiting room staff UI",
                )
                obj, created = TranslationValue.objects.get_or_create(
                    translation_key=key,
                    language_code=lang,
                    defaults={"value": text},
                )
                if created:
                    created_values += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Translation seed finished. Created values: {created_values}."
            )
        )
