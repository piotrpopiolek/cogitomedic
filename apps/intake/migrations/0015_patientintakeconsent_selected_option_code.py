# Generated manually to store optional selected option for consent entries
# (used by contact method consent in tablet form).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0014_fix_praevention_consent_texts"),
    ]

    operations = [
        migrations.AddField(
            model_name="patientintakeconsent",
            name="selected_option_code",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
