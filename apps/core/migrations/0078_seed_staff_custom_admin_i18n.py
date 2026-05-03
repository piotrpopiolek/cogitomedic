# Seed administration.staff_custom_admin_* for shared staff custom admin helpers.

from pathlib import Path

from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=("administration.json",),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0077_seed_paper_intake_admin_ui_strings"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
