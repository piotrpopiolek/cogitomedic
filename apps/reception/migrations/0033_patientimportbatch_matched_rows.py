# XLSX import: count rows matched to existing patients (vs newly inserted).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0032_patient_anonymization_and_nullable_dob"),
    ]

    operations = [
        migrations.AddField(
            model_name="patientimportbatch",
            name="matched_rows",
            field=models.IntegerField(default=0, verbose_name="Matched rows"),
        ),
        migrations.RemoveConstraint(
            model_name="patientimportbatch",
            name="import_batch_non_negative_counts",
        ),
        migrations.AddConstraint(
            model_name="patientimportbatch",
            constraint=models.CheckConstraint(
                condition=models.Q(total_rows__gte=0)
                & models.Q(inserted_rows__gte=0)
                & models.Q(matched_rows__gte=0)
                & models.Q(error_rows__gte=0),
                name="import_batch_non_negative_counts",
            ),
        ),
    ]
