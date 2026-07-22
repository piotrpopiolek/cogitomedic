# Force-update accounting_report_hint (queue_date + M8). Seed is get_or_create-only.

from django.db import migrations
from django.db.models import F

_KEY = "administration.accounting_report_hint"

_VALUES: dict[str, str] = {
    "de-DE": (
        "Zeilen: erste gültige Befund-Veröffentlichung nach Untersuchungsdatum. "
        "Nachkorrekturen erzeugen keine neue Position; nach Widerruf zählt die "
        "nächste Veröffentlichung."
    ),
    "en-GB": (
        "Rows: first valid Befund publication by examination date. Corrections do "
        "not create a new line item; after revoke the next publication counts."
    ),
    "pl-PL": (
        "Wiersze: pierwsza ważna publikacja Befundu wg daty badania. Korekty nie "
        "tworzą nowej pozycji; po cofnięciu publikacji liczy się kolejna publikacja."
    ),
}

_OLD_VALUES: dict[str, str] = {
    "de-DE": (
        "Zeilen: erste Befund-Veröffentlichung nach published_at. Revisionen "
        "erzeugen keine neue Position."
    ),
    "en-GB": (
        "Rows: first Befund publication by published_at date. Revisions do not "
        "create a new line item."
    ),
    "pl-PL": (
        "Wiersze: pierwsza publikacja Befundu wg daty published_at. Rewizje nie "
        "tworzą nowej pozycji."
    ),
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")

    try:
        key = TranslationKey.objects.get(key=_KEY)
    except TranslationKey.DoesNotExist:
        return

    for lang_code, text in _VALUES.items():
        TranslationValue.objects.update_or_create(
            translation_key=key,
            language_code=lang_code,
            defaults={"value": text},
        )

    TranslationCacheVersion.objects.filter(category="administration").update(
        version=F("version") + 1
    )


def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")

    try:
        key = TranslationKey.objects.get(key=_KEY)
    except TranslationKey.DoesNotExist:
        return

    for lang_code, text in _OLD_VALUES.items():
        TranslationValue.objects.filter(
            translation_key=key,
            language_code=lang_code,
        ).update(value=text)

    TranslationCacheVersion.objects.filter(category="administration").update(
        version=F("version") + 1
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0115_seed_accounting_report_queue_date_hint"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
