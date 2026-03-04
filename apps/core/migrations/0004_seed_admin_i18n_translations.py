# Generated manually – seed administration UI translations from admin_i18n (DE, EN, PL).

from django.db import migrations

from cogitomedica.admin_i18n import ADMIN_UI_DE, ADMIN_UI_EN, ADMIN_UI_PL


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    admin_ui_source = {"de": ADMIN_UI_DE, "en": ADMIN_UI_EN, "pl": ADMIN_UI_PL}
    for lang, mapping in admin_ui_source.items():
        for short_key, text in mapping.items():
            full_key = f"administration.{short_key}"
            key, _ = TranslationKey.objects.get_or_create(
                key=full_key,
                defaults={
                    "category": "administration",
                    "description": "Admin panel UI",
                    "is_html_allowed": False,
                    "allowed_placeholders": [],
                    "status": "ACTIVE",
                },
            )
            TranslationValue.objects.get_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": text},
            )


def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    keys_to_delete = [f"administration.{short_key}" for short_key in ADMIN_UI_DE]
    TranslationKey.objects.filter(key__in=keys_to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_add_tablet_consent_translations"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
