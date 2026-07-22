# Accounting report i18n updates (queue_date hint, attended/ausfall/paper, M8, mode labels).
# Squashed former seeds 0115–0122 into this single migration (not yet on production).

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
        ("core", "0114_seed_pagination_nav_and_intake_detail_i18n"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
