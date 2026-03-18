# Update German consent_confirm from "Ich bestätige" to "Ich bin einverstanden".

from django.db import migrations


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    key = TranslationKey.objects.filter(key="waiting_room.form.consent_confirm").first()
    if key:
        TranslationValue.objects.filter(
            translation_key=key,
            language_code="de",
            value="Ich bestätige",
        ).update(value="Ich bin einverstanden")


def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    key = TranslationKey.objects.filter(key="waiting_room.form.consent_confirm").first()
    if key:
        TranslationValue.objects.filter(
            translation_key=key,
            language_code="de",
            value="Ich bin einverstanden",
        ).update(value="Ich bestätige")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_seed_tablet_unassigned_translation"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
