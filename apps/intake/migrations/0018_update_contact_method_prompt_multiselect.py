from django.db import migrations


def update_contact_method_prompt_multiselect(apps, schema_editor):
    ConsentDefinition = apps.get_model("intake", "ConsentDefinition")
    ConsentDefinition.objects.filter(
        code="PRAEVENTIONS_ERINNERUNGEN_KONTAKTWEG",
        version=1,
    ).update(
        content_de="Bitte wählen Sie Ihre bevorzugten Kontaktwege:",
        content_en="Please select your preferred contact methods:",
        content_pl="Proszę wybrać preferowane sposoby kontaktu:",
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0017_patientintakeconsent_selected_option_codes"),
    ]

    operations = [
        migrations.RunPython(update_contact_method_prompt_multiselect, noop_reverse),
    ]
