# Add consent_result_portal_agree label for DS_EINWILLIGUNG_ERGEBNISSES (distinct from consent_contact_agree).

from django.db import migrations

CONSENT_RESULT_PORTAL_AGREE = {
    "de": "Ich bin mit der elektronischen Bereitstellung meines Ergebnisses im Portal einverstanden.",
    "en": "I agree to the electronic provision of my result in the portal.",
    "pl": "Wyrażam zgodę na elektroniczne udostępnienie mojego wyniku w portalu.",
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")

    full_key = "waiting_room.form.consent_result_portal_agree"
    key, _ = TranslationKey.objects.get_or_create(
        key=full_key,
        defaults={
            "category": "waiting_room",
            "description": "Consent checkbox label: result in portal (DS_EINWILLIGUNG_ERGEBNISSES)",
            "is_html_allowed": False,
            "allowed_placeholders": [],
            "status": "ACTIVE",
        },
    )
    for lang, text in CONSENT_RESULT_PORTAL_AGREE.items():
        TranslationValue.objects.get_or_create(
            translation_key=key,
            language_code=lang,
            defaults={"value": text},
        )


def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationKey.objects.filter(key="waiting_room.form.consent_result_portal_agree").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_update_consent_confirm_de"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
