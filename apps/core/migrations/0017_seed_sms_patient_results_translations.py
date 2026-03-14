# Generated manually – seed SMS patient results notification (portal wyniki).

from django.db import migrations

SMS_PATIENT_RESULTS_KEY = "other.sms.patient_results"
DEFAULTS = {
    "de": "Neue Dokumentation bei CogitoMed {url}",
    "en": "New documentation at CogitoMed {url}",
    "pl": "Nowa dokumentacja w CogitoMed {url}",
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    key, _ = TranslationKey.objects.get_or_create(
        key=SMS_PATIENT_RESULTS_KEY,
        defaults={
            "category": "other",
            "description": "SMS text after Befund publish (portal wyniki); placeholder: {url}",
            "is_html_allowed": False,
            "allowed_placeholders": ["url"],
            "status": "ACTIVE",
        },
    )
    for lang, value in DEFAULTS.items():
        TranslationValue.objects.get_or_create(
            translation_key=key,
            language_code=lang,
            defaults={"value": value},
        )


def reverse(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationKey.objects.filter(key=SMS_PATIENT_RESULTS_KEY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_seed_waiting_room_translations"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
