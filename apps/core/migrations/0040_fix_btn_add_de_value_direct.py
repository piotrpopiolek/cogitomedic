# Force-update German value for administration.btn_add.

from django.db import migrations


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    try:
        key = TranslationKey.objects.get(key="administration.btn_add")
    except TranslationKey.DoesNotExist:
        return

    TranslationValue.objects.filter(
        translation_key=key, language_code__in=("de-DE", "de")
    ).update(value="Hinzufügen")


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0039_fix_btn_add_de_translation"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
