# Align Ergebnisse DOB label/placeholder with <input type="date"> (YYYY-MM-DD).
# Seed is get_or_create-only, so existing rows need a force-update.

from django.db import migrations
from django.db.models import F

_UPDATES: dict[str, dict[str, str]] = {
    "other.ergebnisse.dob_label": {
        "de-DE": "Geburtsdatum (JJJJ-MM-TT)",
        "en-GB": "Date of birth (YYYY-MM-DD)",
        "pl-PL": "Data urodzenia (RRRR-MM-DD)",
    },
    "other.ergebnisse.dob_placeholder": {
        "de-DE": "JJJJ-MM-TT",
        "en-GB": "YYYY-MM-DD",
        "pl-PL": "RRRR-MM-DD",
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
        ("core", "0118_seed_patient_result_available_sms_i18n"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
