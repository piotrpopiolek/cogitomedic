# Data migration: remove pseudo-checkbox glyphs from prevention consents
# and align consent text with UI checkbox label behavior.

from django.db import migrations


def update_prevention_consents_content(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")

    ConsentDefinition.objects.filter(
        code="PRAEVENTIONS_ERINNERUNGEN_EINWILLIGUNG",
        version=1,
    ).update(
        content_de=(
            "Möchten Sie zukünftig an empfohlene Vorsorgeuntersuchungen erinnert werden "
            "und Informationen zu weiteren Gesundheitsangeboten erhalten?"
        ),
        content_en=(
            "Would you like to be reminded about recommended preventive examinations in "
            "the future and receive information about other health services?"
        ),
        content_pl=(
            "Czy chciałbyś/chciałabyś w przyszłości otrzymywać przypomnienia o zalecanych "
            "badaniach profilaktycznych oraz informacje o innych ofertach zdrowotnych?"
        ),
    )

    ConsentDefinition.objects.filter(
        code="PRAEVENTIONS_ERINNERUNGEN_KONTAKTWEG",
        version=1,
    ).update(
        content_de="Bevorzugter Kontaktweg:\nE-Mail\nSMS\nTelefon",
        content_en="Preferred contact method:\nEmail\nSMS\nPhone",
        content_pl="Preferowany sposób kontaktu:\nE-mail\nSMS\nTelefon",
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0013_consent_praeventions_erinnerungen_en_pl"),
    ]

    operations = [
        migrations.RunPython(update_prevention_consents_content, noop_reverse),
    ]
