from django.db import migrations, models


def fill_selected_option_codes(apps, schema_editor):
    PatientIntakeConsent = apps.get_model("intake", "PatientIntakeConsent")
    for pic in PatientIntakeConsent.objects.all().iterator():
        one = (pic.selected_option_code or "").strip()
        pic.selected_option_codes = [one] if one else []
        pic.save(update_fields=["selected_option_codes"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0016_update_contact_method_prompt_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="patientintakeconsent",
            name="selected_option_codes",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(fill_selected_option_codes, noop_reverse),
    ]
