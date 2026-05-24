# Restore patient_identity_unique; drop global UNIQUE(phone) for shared family numbers.

from django.db import migrations, models
from django.db.models import Count


def assert_no_duplicate_patient_identity(apps, schema_editor):
    Patient = apps.get_model("reception", "Patient")
    db_alias = schema_editor.connection.alias

    duplicates = list(
        Patient.objects.using(db_alias)
        .values("first_name", "last_name", "phone", "date_of_birth")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)[:5]
    )
    if not duplicates:
        return

    details = ", ".join(
        (
            f"{item['first_name']} {item['last_name']} / {item['phone']} / "
            f"{item['date_of_birth']} ({item['row_count']})"
        )
        for item in duplicates
    )
    raise RuntimeError(
        "Cannot add patient_identity_unique because duplicate patient rows exist: "
        f"{details}"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("reception", "0039_work_queue_perf_indexes"),
    ]

    operations = [
        migrations.RunPython(
            assert_no_duplicate_patient_identity,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="patient",
            name="patient_phone_unique",
        ),
        migrations.AddConstraint(
            model_name="patient",
            constraint=models.UniqueConstraint(
                fields=("first_name", "last_name", "phone", "date_of_birth"),
                name="patient_identity_unique",
            ),
        ),
    ]
