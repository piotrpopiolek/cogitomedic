# Seed doctor.rec_followup_12 (Befund section 10: 12-month follow-up option).

from pathlib import Path

from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=("doctor_ui.json",),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0050_seed_medical_outbox_patient_results_labels"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
