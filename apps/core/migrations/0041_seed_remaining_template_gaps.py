# Seed remaining template i18n keys moved to system 1.

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
            "administration_templates.json",
            "other.json",
            "waiting_room_staff.json",
            "waiting_room_form.json",
            "doctor_ui.json",
        ),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0040_fix_btn_add_de_value_direct"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
