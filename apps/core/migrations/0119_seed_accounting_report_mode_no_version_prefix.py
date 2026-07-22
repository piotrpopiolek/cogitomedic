# Accounting report mode labels: drop v1/v2 prefixes.

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
        ("core", "0118_seed_accounting_report_mode_labels_plain"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
