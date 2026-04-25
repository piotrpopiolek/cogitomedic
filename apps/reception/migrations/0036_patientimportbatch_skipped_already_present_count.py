from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0035_alter_patientformsession_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="patientimportbatch",
            name="skipped_already_present_count",
            field=models.IntegerField(default=0, verbose_name="Skipped already present rows"),
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
                & models.Q(skipped_already_present_count__gte=0)
                & models.Q(error_rows__gte=0),
                name="import_batch_non_negative_counts",
            ),
        ),
    ]
