"""Backfill patient.phone to normalize_phone_for_patient_storage (libphonenumber)."""

from django.db import migrations


def normalize_patient_phones(apps, schema_editor):
    from apps.reception.models import Patient
    from apps.reception.patient_identity import normalize_patient_phone_for_storage

    for patient in Patient.objects.iterator(chunk_size=200):
        if (patient.first_name or "").strip().upper() == "ANONYMIZED":
            continue
        new_phone = normalize_patient_phone_for_storage(patient.phone or "")
        if not new_phone or new_phone == patient.phone:
            continue
        patient.phone = new_phone
        patient.save(update_fields=["phone", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("reception", "0041_normalize_patient_name_casing"),
    ]

    operations = [
        migrations.RunPython(normalize_patient_phones, migrations.RunPython.noop),
    ]
