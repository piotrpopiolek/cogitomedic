# Generated manually – update doctor UI strings after removing generate-text

from django.db import migrations


# New values: no reference to "Generate text" / "Text generieren" / "Generuj tekst"
DOCTOR_TEXT_PLACEHOLDER = {
    "de": "Text hier anzeigen und bearbeiten",
    "en": "Display and edit content here.",
    "pl": "Treść tutaj (można edytować).",
}
DOCTOR_BTN_GENERATE = {
    "de": "—",
    "en": "—",
    "pl": "—",
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    for full_key, lang_to_text in [
        ("doctor.text_placeholder", DOCTOR_TEXT_PLACEHOLDER),
        ("doctor.btn_generate", DOCTOR_BTN_GENERATE),
    ]:
        try:
            key = TranslationKey.objects.get(key=full_key)
        except TranslationKey.DoesNotExist:
            continue
        for lang, text in lang_to_text.items():
            TranslationValue.objects.update_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": text},
            )


def backward(apps, schema_editor):
    pass  # Leave updated values in place


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_update_real_field_translations"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
