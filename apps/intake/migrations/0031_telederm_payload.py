from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0030_process_type_allowed"),
    ]

    operations = [
        migrations.AddField(
            model_name="patientintakeform",
            name="telederm_schema_version",
            field=models.SmallIntegerField(
                default=0,
                verbose_name="Telederm schema version",
            ),
        ),
        migrations.AddField(
            model_name="patientintakeform",
            name="telederm_payload",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="Telederm payload",
            ),
        ),
    ]
