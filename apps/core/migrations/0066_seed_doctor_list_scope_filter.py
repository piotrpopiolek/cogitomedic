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


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0065_seed_admin_col_last_login"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
