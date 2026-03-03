# Generated manually

from django.db import migrations

def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    
    translations = [
        {
            "key": "waiting_room.form.contact_method_phone",
            "category": "waiting_room",
            "description": "Phone contact method in tablet form",
            "values": {
                "de": "Telefon",
                "en": "Phone",
                "pl": "Telefon",
            }
        },
        {
            "key": "waiting_room.form.consent_contact_agree",
            "category": "waiting_room",
            "description": "Agreement for contact method consent in tablet form",
            "values": {
                "de": "Ja, ich bin mit einer Kontaktaufnahme einverstanden.",
                "en": "Yes, I agree to be contacted.",
                "pl": "Tak, wyrażam zgodę na kontakt.",
            }
        },
    ]
    
    for item in translations:
        t_key, created = TranslationKey.objects.get_or_create(
            key=item["key"],
            defaults={
                "category": item["category"],
                "description": item["description"],
                "status": "ACTIVE",
            }
        )
        for lang, value in item["values"].items():
            TranslationValue.objects.get_or_create(
                translation_key=t_key,
                language_code=lang,
                defaults={"value": value}
            )

def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationKey.objects.filter(
        key__in=[
            "waiting_room.form.contact_method_phone",
            "waiting_room.form.consent_contact_agree"
        ]
    ).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_rename_translation__categor_f7ee83_idx_translation_categor_5887cc_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
