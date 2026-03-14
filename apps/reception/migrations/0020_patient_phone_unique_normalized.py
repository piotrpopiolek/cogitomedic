# Normalize phone to digits only, merge duplicates by phone, add UNIQUE(phone).

import re

from django.db import migrations, models


def _normalize_phone(value: str) -> str:
    """Digits only, min 7 chars."""
    if not value or not isinstance(value, str):
        return ""
    digits = re.sub(r"[^\d]", "", value.strip())
    return digits if len(digits) >= 7 else ""


def normalize_and_dedupe_phones(apps, schema_editor):
    Patient = apps.get_model("reception", "Patient")
    PatientContactHistory = apps.get_model("reception", "PatientContactHistory")
    QueueEntry = apps.get_model("reception", "QueueEntry")
    PatientResultsOtpSession = apps.get_model("patient_results", "PatientResultsOtpSession")
    db_alias = schema_editor.connection.alias

    # 1. Normalize all phones
    for p in Patient.objects.using(db_alias).iterator():
        norm = _normalize_phone(p.phone)
        if norm and norm != p.phone:
            p.phone = norm
            p.save(update_fields=["phone", "updated_at"])

    # 2. Find and merge duplicates by phone
    from django.db.models import Count

    dup_groups = list(
        Patient.objects.using(db_alias)
        .values("phone")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
    )

    for group in dup_groups:
        patients = list(
            Patient.objects.using(db_alias)
            .filter(phone=group["phone"])
            .order_by("created_at", "id")
        )
        keeper = patients[0]
        for dup in patients[1:]:
            # Reassign FKs
            QueueEntry.objects.using(db_alias).filter(patient_id=dup.id).update(patient_id=keeper.id)
            PatientContactHistory.objects.using(db_alias).filter(patient_id=dup.id).update(
                patient_id=keeper.id
            )
            PatientResultsOtpSession.objects.using(db_alias).filter(patient_id=dup.id).update(
                patient_id=keeper.id
            )
            for clinic_site in dup.clinic_sites.using(db_alias).all():
                keeper.clinic_sites.add(clinic_site)
            dup.delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("reception", "0019_clinicsite_pdf_import_config"),
        ("patient_results", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(normalize_and_dedupe_phones, noop),
        migrations.RemoveConstraint(
            model_name="patient",
            name="patient_identity_unique",
        ),
        migrations.RemoveConstraint(
            model_name="patient",
            name="patient_phone_format",
        ),
        migrations.AddConstraint(
            model_name="patient",
            constraint=models.UniqueConstraint(
                fields=("phone",),
                name="patient_phone_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="patient",
            constraint=models.CheckConstraint(
                condition=models.Q(phone__regex=r"^[0-9]{7,20}$"),
                name="patient_phone_format",
            ),
        ),
    ]
