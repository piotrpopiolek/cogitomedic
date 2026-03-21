from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0028_seed_queue_20_patients_2026_03_19"),
    ]

    operations = [
        migrations.DeleteModel(
            name="PatientContactHistory",
        ),
    ]
