# Denormalized sort key for doctor work queue (digital / paper / mixed eligibility).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0037_drop_queue_entry_status_published"),
    ]

    operations = [
        migrations.AddField(
            model_name="queueentry",
            name="doctor_list_sort_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Doctor list sort time",
            ),
        ),
        migrations.AddIndex(
            model_name="queueentry",
            index=models.Index(
                fields=["-doctor_list_sort_at"],
                name="qentry_doctor_sort_idx",
                condition=models.Q(doctor_list_sort_at__isnull=False),
            ),
        ),
    ]
