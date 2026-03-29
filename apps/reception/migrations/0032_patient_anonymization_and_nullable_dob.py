# US-013: Patient anonymization fields + nullable date_of_birth.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0031_dailyqueue_assigned_doctor_doctor_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="anonymization_started_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Anonymization started at",
            ),
        ),
        migrations.AddField(
            model_name="patient",
            name="anonymized_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Anonymized at",
            ),
        ),
        migrations.AddField(
            model_name="patient",
            name="consent_summary",
            field=models.JSONField(
                blank=True,
                null=True,
                verbose_name="Consent summary",
            ),
        ),
        migrations.AlterField(
            model_name="patient",
            name="date_of_birth",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Date of birth",
            ),
        ),
    ]
