# Seed model_* intake/tablet/translation + app_intake DE; side_* / field_daily_queue DE tweaks.

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
            "administration.json",
            "administration_apps.json",
            "administration_fields.json",
        ),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0047_seed_reception_admin_labels_and_recent_actions"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
