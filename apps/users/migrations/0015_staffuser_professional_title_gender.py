# Generated manually for Befund PDF footer (Facharzt / Fachärztin).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0014_rename_klinikleitung_group_to_manager"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffuser",
            name="professional_title",
            field=models.CharField(
                blank=True,
                default="Dr. med.",
                max_length=80,
                verbose_name="Professional title (PDF)",
            ),
        ),
        migrations.AddField(
            model_name="staffuser",
            name="gender",
            field=models.CharField(
                choices=[
                    ("UNSPECIFIED", "Not specified"),
                    ("FEMALE", "Female"),
                    ("MALE", "Male"),
                ],
                default="UNSPECIFIED",
                max_length=20,
                verbose_name="Gender (PDF footer)",
            ),
        ),
    ]
