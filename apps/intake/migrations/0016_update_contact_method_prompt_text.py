# Data migration: make contact-method consent content a prompt only.
# Options are rendered as real radio inputs in tablet UI.

from django.db import migrations


def update_contact_method_prompt(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    ConsentDefinition.objects.filter(
        code="PRAEVENTIONS_ERINNERUNGEN_KONTAKTWEG",
        version=1,
    ).update(
        content_de="Bitte wählen Sie Ihren bevorzugten Kontaktweg:",
        content_en="Please select your preferred contact method:",
        content_pl="Proszę wybrać preferowany sposób kontaktu:",
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0015_patientintakeconsent_selected_option_code"),
    ]

    operations = [
        migrations.RunPython(update_contact_method_prompt, noop_reverse),
    ]
