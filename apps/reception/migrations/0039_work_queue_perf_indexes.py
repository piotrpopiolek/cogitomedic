from django.contrib.postgres.indexes import GinIndex
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reception", "0038_queueentry_doctor_list_sort_at"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddIndex(
            model_name="patient",
            index=GinIndex(
                fields=["last_name"],
                name="patient_last_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="patient",
            index=GinIndex(
                fields=["first_name"],
                name="patient_first_name_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="queueentry",
            index=models.Index(
                fields=["entry_status", "-doctor_list_sort_at", "-id"],
                name="qentry_doc_queue_perf_idx",
                condition=models.Q(
                    doctor_list_sort_at__isnull=False,
                    entry_status__in=[
                        "WAITING",
                        "PATIENT_COMPLETED",
                        "PAPER_INTAKE_COMPLETED",
                    ],
                ),
            ),
        ),
    ]
