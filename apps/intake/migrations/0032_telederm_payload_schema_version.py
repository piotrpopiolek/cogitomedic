from django.db import migrations, models

import apps.intake.constants


def backfill_telederm_json_schema_version(apps, schema_editor):
    """Set column version 0 and JSON missing/0 ``schema_version`` to 1."""
    PatientIntakeForm = apps.get_model("intake", "PatientIntakeForm")
    schema_version = 1
    batch = []
    batch_size = 500
    for form in PatientIntakeForm.objects.all().iterator(chunk_size=batch_size):
        payload = form.telederm_payload
        if not isinstance(payload, dict):
            payload = {}
        else:
            payload = dict(payload)
        changed = False
        if form.telederm_schema_version == 0:
            form.telederm_schema_version = schema_version
            changed = True
        if payload.get("schema_version") in (None, 0):
            payload["schema_version"] = schema_version
            form.telederm_payload = payload
            changed = True
        if not changed:
            continue
        batch.append(form)
        if len(batch) >= batch_size:
            PatientIntakeForm.objects.bulk_update(
                batch, ["telederm_schema_version", "telederm_payload"]
            )
            batch = []
    if batch:
        PatientIntakeForm.objects.bulk_update(
            batch, ["telederm_schema_version", "telederm_payload"]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0031_telederm_payload"),
    ]

    operations = [
        migrations.RunPython(
            backfill_telederm_json_schema_version,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="patientintakeform",
            name="telederm_schema_version",
            field=models.SmallIntegerField(
                default=1,
                verbose_name="Telederm schema version",
            ),
        ),
        migrations.AlterField(
            model_name="patientintakeform",
            name="telederm_payload",
            field=models.JSONField(
                blank=True,
                default=apps.intake.constants.default_telederm_payload,
                verbose_name="Telederm payload",
            ),
        ),
    ]
