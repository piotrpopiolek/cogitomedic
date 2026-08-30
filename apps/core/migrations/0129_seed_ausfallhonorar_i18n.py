# Seed Ausfallhonorar field/action/domain strings and update the report hint.

from pathlib import Path

from django.conf import settings
from django.db import migrations
from django.db.models import F

_UPDATE_EXISTING: dict[str, dict[str, str]] = {
    "administration.accounting_report_hint_ausfall": {
        "de-DE": (
            "Zeilen: nur manuell markierte Ausfallhonorar-Einträge im gewählten "
            "Untersuchungszeitraum. Markierung durch Empfang, Manager oder Admin. "
            "Unabhängig vom Anamnesestatus oder Storno."
        ),
        "en-GB": (
            "Rows: only visits staff marked as Ausfallhonorar in the selected "
            "exam-date range. Reception, Manager, or Admin set the flag. "
            "Independent of questionnaire status or cancellation."
        ),
        "pl-PL": (
            "Wiersze: tylko wizyty ręcznie oznaczone jako Ausfallhonorar w wybranym "
            "zakresie dat badania. Flagę ustawia recepcja, manager lub administrator. "
            "Niezależnie od statusu ankiety i anulowania."
        ),
    },
    "other.api.provide_entry_status_or_notes": {
        "de-DE": "entry_status, notes und/oder ausfallhonorar angeben.",
        "en-GB": "Provide entry_status, notes, and/or ausfallhonorar.",
        "pl-PL": "Podaj entry_status, notes i/lub ausfallhonorar.",
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
        only_json_filenames=(
            "administration.json",
            "administration_fields.json",
            "other_api.json",
            "other_domain.json",
        ),
    )
    _update_translation_values(apps, _UPDATE_EXISTING)
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")
    TranslationCacheVersion.objects.filter(
        category__in=["administration", "other"]
    ).update(version=F("version") + 1)


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0128_seed_edit_session_error_i18n"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
