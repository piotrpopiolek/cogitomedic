# Add TabletDevice.clinic_site (FK to ClinicSite). Tablet sees only queues of this site.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0023_seed_queue_second_site_2026_03_15"),
    ]

    operations = [
        migrations.AddField(
            model_name="tabletdevice",
            name="clinic_site",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tablet_devices",
                to="reception.clinicsite",
                verbose_name="Clinic site",
            ),
        ),
    ]
