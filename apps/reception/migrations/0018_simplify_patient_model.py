from django.db import migrations, models
from django.db.models import Count


def ensure_unique_patient_identity(apps, schema_editor):
    Patient = apps.get_model("reception", "Patient")
    PatientContactHistory = apps.get_model("reception", "PatientContactHistory")
    QueueEntry = apps.get_model("reception", "QueueEntry")
    db_alias = schema_editor.connection.alias

    duplicate_groups = list(
        Patient.objects.using(db_alias)
        .values("first_name", "last_name", "phone", "date_of_birth")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
    )

    for group in duplicate_groups:
        patients = list(
            Patient.objects.using(db_alias)
            .filter(
                first_name=group["first_name"],
                last_name=group["last_name"],
                phone=group["phone"],
                date_of_birth=group["date_of_birth"],
            )
            .order_by("created_at", "id")
        )
        patients.sort(key=lambda item: (item.doctolib_patient_id is None, item.created_at, str(item.id)))
        keeper = patients[0]
        duplicates = patients[1:]

        for duplicate in duplicates:
            if (
                keeper.doctolib_patient_id
                and duplicate.doctolib_patient_id
                and keeper.doctolib_patient_id != duplicate.doctolib_patient_id
            ):
                raise RuntimeError(
                    "Cannot automatically merge duplicate patients with different doctolib_patient_id "
                    f"values for {group['first_name']} {group['last_name']} / {group['phone']} / "
                    f"{group['date_of_birth']}."
                )

            update_fields = []
            if not keeper.doctolib_patient_id and duplicate.doctolib_patient_id:
                keeper.doctolib_patient_id = duplicate.doctolib_patient_id
                update_fields.append("doctolib_patient_id")
            for field_name in ("email", "street", "city", "postal_code", "country_code"):
                if not getattr(keeper, field_name) and getattr(duplicate, field_name):
                    setattr(keeper, field_name, getattr(duplicate, field_name))
                    update_fields.append(field_name)
            if not keeper.is_active and duplicate.is_active:
                keeper.is_active = True
                update_fields.append("is_active")
            if update_fields:
                keeper.save(update_fields=update_fields)

            QueueEntry.objects.using(db_alias).filter(patient_id=duplicate.id).update(patient_id=keeper.id)
            PatientContactHistory.objects.using(db_alias).filter(patient_id=duplicate.id).update(
                patient_id=keeper.id
            )
            for clinic_site in duplicate.clinic_sites.using(db_alias).all():
                keeper.clinic_sites.add(clinic_site)
            duplicate.delete()

    duplicates = list(
        Patient.objects.using(db_alias)
        .values("first_name", "last_name", "phone", "date_of_birth")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)[:5]
    )
    if duplicates:
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

    atomic = False

    dependencies = [
        ("reception", "0017_seed_queue_20_patients_2026_03_08"),
    ]

    operations = [
        migrations.RunPython(ensure_unique_patient_identity, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="patient",
            name="patient_identit_749f01_idx",
        ),
        migrations.RemoveConstraint(
            model_name="patient",
            name="patient_external_unique",
        ),
        migrations.RemoveConstraint(
            model_name="patient",
            name="patient_identity_status_valid",
        ),
        migrations.RemoveConstraint(
            model_name="patient",
            name="patient_temp_identity_requires_alert",
        ),
        migrations.RemoveConstraint(
            model_name="patient",
            name="patient_identity_due_after_alert",
        ),
        migrations.RemoveField(
            model_name="patient",
            name="identity_status",
        ),
        migrations.RemoveField(
            model_name="patient",
            name="identity_alert_created_at",
        ),
        migrations.RemoveField(
            model_name="patient",
            name="identity_resolution_due_at",
        ),
        migrations.RemoveField(
            model_name="patient",
            name="external_source",
        ),
        migrations.RemoveField(
            model_name="patient",
            name="external_source_id",
        ),
        migrations.AddConstraint(
            model_name="patient",
            constraint=models.UniqueConstraint(
                fields=("first_name", "last_name", "phone", "date_of_birth"),
                name="patient_identity_unique",
            ),
        ),
    ]
