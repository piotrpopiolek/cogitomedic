from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0025_patientintakeform_reopen_reception_note"),
    ]

    operations = [
        migrations.AlterField(
            model_name="intakeoutboxevent",
            name="max_retries",
            field=models.SmallIntegerField(default=3),
        ),
    ]
