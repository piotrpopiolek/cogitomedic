# Denormalized HiDrive /incoming filename keys for patient-level matching (no full-table scan).

from django.db import migrations, models


def forwards(apps, schema_editor):
    Patient = apps.get_model("reception", "Patient")
    from apps.medical.name_normalize import compute_incoming_pdf_name_keys

    batch: list = []
    for p in Patient.objects.iterator(chunk_size=500):
        fl, lf = compute_incoming_pdf_name_keys(p.first_name, p.last_name)
        p.incoming_pdf_name_key_fl = fl[:300]
        p.incoming_pdf_name_key_lf = lf[:300]
        batch.append(p)
        if len(batch) >= 500:
            Patient.objects.bulk_update(
                batch, ["incoming_pdf_name_key_fl", "incoming_pdf_name_key_lf"]
            )
            batch.clear()
    if batch:
        Patient.objects.bulk_update(
            batch, ["incoming_pdf_name_key_fl", "incoming_pdf_name_key_lf"]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("reception", "0033_patientimportbatch_matched_rows"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="incoming_pdf_name_key_fl",
            field=models.CharField(
                default="",
                editable=False,
                max_length=300,
                verbose_name="Incoming PDF name key (first_last)",
            ),
        ),
        migrations.AddField(
            model_name="patient",
            name="incoming_pdf_name_key_lf",
            field=models.CharField(
                default="",
                editable=False,
                max_length=300,
                verbose_name="Incoming PDF name key (last_first)",
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="patient",
            index=models.Index(
                fields=["incoming_pdf_name_key_fl"],
                name="patient_incoming_pdf_key_fl_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="patient",
            index=models.Index(
                fields=["incoming_pdf_name_key_lf"],
                name="patient_incoming_pdf_key_lf_idx",
            ),
        ),
    ]
