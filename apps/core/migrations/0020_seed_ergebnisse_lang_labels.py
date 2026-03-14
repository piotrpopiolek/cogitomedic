# Add lang_de, lang_en, lang_pl for ergebnisse flag titles (tooltips).

from django.db import migrations

LANG_LABELS = {
    "lang_de": {"de": "Deutsch", "en": "Deutsch", "pl": "Deutsch"},
    "lang_en": {"de": "English", "en": "English", "pl": "English"},
    "lang_pl": {"de": "Polski", "en": "Polski", "pl": "Polski"},
}
PREFIX = "other.ergebnisse."


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    for short_key, lang_values in LANG_LABELS.items():
        full_key = f"{PREFIX}{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "other",
                "description": f"Ergebnisse: language label for {short_key}",
                "is_html_allowed": False,
                "allowed_placeholders": [],
                "status": "ACTIVE",
            },
        )
        for lang, value in lang_values.items():
            TranslationValue.objects.get_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": value},
            )


def reverse(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    for k in LANG_LABELS:
        TranslationKey.objects.filter(key=f"{PREFIX}{k}").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_seed_ergebnisse_translations"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
