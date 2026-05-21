# Remove default professional title; title is optional (PDF footer + admin).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0017_alter_staffuser_gender_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="staffuser",
            name="professional_title",
            field=models.CharField(
                blank=True,
                default="",
                max_length=80,
                verbose_name="Professional title",
            ),
        ),
    ]
