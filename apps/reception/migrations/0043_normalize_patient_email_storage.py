"""Backfill Patient.email: strip whitespace/NBSP and lowercase."""

from django.db import migrations


def normalize_patient_emails(apps, schema_editor):
    from apps.reception.models import Patient
    from apps.reception.patient_identity import normalize_email_for_storage

    for patient in Patient.objects.iterator(chunk_size=200):
        if (patient.first_name or "").strip().upper() == "ANONYMIZED":
            continue
        new_email = normalize_email_for_storage(patient.email or "")
        if not new_email or new_email == patient.email:
            continue
        patient.email = new_email
        patient.save(update_fields=["email", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("reception", "0042_normalize_patient_phone_storage"),
    ]

    operations = [
        migrations.RunPython(normalize_patient_emails, migrations.RunPython.noop),
    ]
