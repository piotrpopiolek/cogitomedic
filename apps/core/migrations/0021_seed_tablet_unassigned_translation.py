# Seed waiting_room.staff.tablet_unassigned (tablet not assigned to clinic site message).

from django.db import migrations

TABLET_UNASSIGNED = {
    "de": "Tablet ist keiner Standort zugeordnet. Bitte wenden Sie sich an den Administrator.",
    "en": "Tablet is not assigned to a clinic site. Please contact the administrator.",
    "pl": "Tablet nie jest przypisany do placówki. Skontaktuj się z administratorem.",
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    full_key = "waiting_room.staff.tablet_unassigned"
    key, _ = TranslationKey.objects.get_or_create(
        key=full_key,
        defaults={
            "category": "waiting_room",
            "description": "Message when tablet device has no clinic_site assigned",
            "is_html_allowed": False,
            "allowed_placeholders": [],
            "status": "ACTIVE",
        },
    )
    for lang, text in TABLET_UNASSIGNED.items():
        TranslationValue.objects.get_or_create(
            translation_key=key,
            language_code=lang,
            defaults={"value": text},
        )


def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationKey.objects.filter(key="waiting_room.staff.tablet_unassigned").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_seed_ergebnisse_lang_labels"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
