# Generated manually – seed doctor.template_select_hint for i18n

from django.db import migrations

DOCTOR_TEMPLATE_SELECT_HINT = {
    "de": "Vorlage wählen – danach erscheinen die Favoriten in Abschnitt 8 und 9.",
    "en": "Choose a template – favorites for sections 8 and 9 will then appear.",
    "pl": "Wybierz szablon – wówczas pojawią się ulubione w sekcjach 8 i 9.",
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    key, _ = TranslationKey.objects.get_or_create(
        key="doctor.template_select_hint",
        defaults={
            "category": "doctor",
            "description": "Doctor UI – hint under template select",
            "is_html_allowed": False,
            "allowed_placeholders": [],
            "status": "ACTIVE",
        },
    )
    for lang, text in DOCTOR_TEMPLATE_SELECT_HINT.items():
        TranslationValue.objects.update_or_create(
            translation_key=key,
            language_code=lang,
            defaults={"value": text},
        )


def backward(apps, schema_editor):
    pass  # Leave in place


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_update_doctor_ui_after_remove_generate_text"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
