# Re-seed: StaffUser PDF footer labels, doctor list scope / revision chip, PDF signoff lines.

from pathlib import Path

from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=(
            "administration_fields.json",
            "doctor_pdf_labels.json",
            "doctor_ui.json",
        ),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0068_seed_other_api_invalid_save_draft_intent"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
