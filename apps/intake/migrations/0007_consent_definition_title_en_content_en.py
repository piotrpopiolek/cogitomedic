# Add English title and content to ConsentDefinition (for form_locale en).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0006_consent_datenschutz_einwilligungen"),
    ]

    operations = [
        migrations.AddField(
            model_name="consentdefinition",
            name="title_en",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="consentdefinition",
            name="content_en",
            field=models.TextField(blank=True, default=""),
        ),
    ]
