# Reception dashboard title, sidebar label, hidrive_hours_waiting placeholder fix.

from pathlib import Path

from django.conf import settings
from django.db import migrations
from django.db.models import F

_HOURS_WAITING_VALUES = {
    "administration.hidrive_hours_waiting": {
        "de-DE": "{hours} h",
        "en-GB": "{hours} h",
        "pl-PL": "{hours} h",
    },
}


def _update_translation_values(apps, values_by_key: dict[str, dict[str, str]]) -> None:
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    for key_str, per_lang in values_by_key.items():
        try:
            key = TranslationKey.objects.get(key=key_str)
        except TranslationKey.DoesNotExist:
            continue
        for lang_code, text in per_lang.items():
            TranslationValue.objects.update_or_create(
                translation_key=key,
                language_code=lang_code,
                defaults={"value": text},
            )


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=("administration.json",),
    )
    _update_translation_values(apps, _HOURS_WAITING_VALUES)
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")
    TranslationCacheVersion.objects.filter(category="administration").update(
        version=F("version") + 1
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0110_seed_hidrive_missing_results_dashboard_i18n"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
