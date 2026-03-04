# Generated manually – seed administration UI field translations.

from django.db import migrations

def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    field_translations = {
        "field_code": {
            "de": "Code",
            "en": "Code",
            "pl": "Kod"
        },
        "field_name": {
            "de": "Name",
            "en": "Name",
            "pl": "Nazwa"
        },
        "field_clinicsite": {
            "de": "Standort",
            "en": "Clinic site",
            "pl": "Placówka"
        },
        "field_is_active": {
            "de": "Ist aktiv",
            "en": "Is active",
            "pl": "Czy aktywny"
        },
        "field_created_at": {
            "de": "Erstellt am",
            "en": "Created at",
            "pl": "Utworzono"
        },
        "field_updated_at": {
            "de": "Aktualisiert am",
            "en": "Updated at",
            "pl": "Zaktualizowano"
        },
    }

    for short_key, mapping in field_translations.items():
        full_key = f"administration.{short_key}"
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "administration",
                "description": "Admin panel field labels",
                "is_html_allowed": False,
                "allowed_placeholders": [],
                "status": "ACTIVE",
            },
        )
        for lang, text in mapping.items():
            TranslationValue.objects.get_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": text},
            )

def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    keys_to_delete = [
        "administration.field_code",
        "administration.field_name",
        "administration.field_clinicsite",
        "administration.field_is_active",
        "administration.field_created_at",
        "administration.field_updated_at",
    ]
    TranslationKey.objects.filter(key__in=keys_to_delete).delete()

class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_seed_admin_menu_translations"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
