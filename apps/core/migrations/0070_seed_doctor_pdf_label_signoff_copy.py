# Update doctor PDF label strings (Facharzt / Fachärztin wording, EN copy).

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
        ("core", "0069_seed_staffuser_pdf_footer_and_doctor_scope_ui"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
