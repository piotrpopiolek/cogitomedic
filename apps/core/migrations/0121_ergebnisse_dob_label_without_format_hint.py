# DOB label without format hint — native <input type="date"> uses browser locale.

from django.db import migrations
from django.db.models import F

_UPDATES: dict[str, dict[str, str]] = {
    "other.ergebnisse.dob_label": {
        "de-DE": "Geburtsdatum",
        "en-GB": "Date of birth",
        "pl-PL": "Data urodzenia",
    },
    "other.ergebnisse.dob_placeholder": {
        "de-DE": "Geburtsdatum",
        "en-GB": "Date of birth",
        "pl-PL": "Data urodzenia",
    },
}

_OLD: dict[str, dict[str, str]] = {
    "other.ergebnisse.dob_label": {
        "de-DE": "Geburtsdatum (TT.MM.JJJJ)",
        "en-GB": "Date of birth (DD.MM.YYYY)",
        "pl-PL": "Data urodzenia (DD.MM.RRRR)",
    },
    "other.ergebnisse.dob_placeholder": {
        "de-DE": "TT.MM.JJJJ",
        "en-GB": "DD.MM.YYYY",
        "pl-PL": "DD.MM.RRRR",
    },
}


def _apply(apps, mapping: dict[str, dict[str, str]]) -> None:
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")

    for key_name, values in mapping.items():
        try:
            key = TranslationKey.objects.get(key=key_name)
        except TranslationKey.DoesNotExist:
            continue
        for lang_code, text in values.items():
            TranslationValue.objects.update_or_create(
                translation_key=key,
                language_code=lang_code,
                defaults={"value": text},
            )

    TranslationCacheVersion.objects.filter(category="other").update(
        version=F("version") + 1
    )


def forward(apps, schema_editor):
    _apply(apps, _UPDATES)


def backward(apps, schema_editor):
    _apply(apps, _OLD)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0120_restore_ergebnisse_dob_dd_mm_yyyy_i18n"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
