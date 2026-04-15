# Re-seed doctor_pdf_labels.json (Läsionen Nummer heading on Befund PDF).

from pathlib import Path

from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=("doctor_pdf_labels.json",),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0059_seed_doctor_pdf_reporting_physician"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
