from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("reception", "0018_simplify_patient_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicsite",
            name="pdf_import_default_consulting_room",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="reception.consultingroom",
                verbose_name="PDF import default consulting room",
            ),
        ),
        migrations.AddField(
            model_name="clinicsite",
            name="pdf_import_shift_code",
            field=models.CharField(
                choices=[
                    ("FULL_DAY", "Full day"),
                    ("MORNING", "Morning"),
                    ("AFTERNOON", "Afternoon"),
                    ("EVENING", "Evening"),
                ],
                default="FULL_DAY",
                max_length=20,
                verbose_name="PDF import shift code",
            ),
        ),
    ]
