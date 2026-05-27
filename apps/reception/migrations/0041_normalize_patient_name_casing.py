"""Backfill title-case patient names so identity lookups match Patient.save()."""

from django.db import IntegrityError, migrations


def normalize_existing_patient_names(apps, schema_editor):
    from apps.reception.models import Patient
    from apps.reception.patient_identity import normalize_patient_name_for_storage

    for patient in (
        Patient.objects.filter(anonymized_at__isnull=True)
        .exclude(first_name__iexact="ANONYMIZED")
        .iterator(chunk_size=200)
    ):
        new_first = normalize_patient_name_for_storage(patient.first_name or "")
        new_last = normalize_patient_name_for_storage(patient.last_name or "")
        if new_first == patient.first_name and new_last == patient.last_name:
            continue
        patient.first_name = new_first
        patient.last_name = new_last
        try:
            patient.save(
                update_fields=[
                    "first_name",
                    "last_name",
                    "incoming_pdf_name_key_fl",
                    "incoming_pdf_name_key_lf",
                ],
            )
        except IntegrityError as exc:
            raise RuntimeError(
                "Cannot normalize patient name casing: duplicate identity would result "
                f"for patient id={patient.id} "
                f"({new_first!r} {new_last!r} / {patient.phone} / {patient.date_of_birth}). "
                "Resolve duplicate rows manually, then re-run migrate."
            ) from exc


class Migration(migrations.Migration):
    dependencies = [
        ("reception", "0040_restore_patient_identity_unique"),
    ]

    operations = [
        migrations.RunPython(
            normalize_existing_patient_names,
            migrations.RunPython.noop,
        ),
    ]
