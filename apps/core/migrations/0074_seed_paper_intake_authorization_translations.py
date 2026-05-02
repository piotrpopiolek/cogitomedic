# Seed translations for paper intake authorization (admin + domain + API).

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
            "other_domain.json",
            "other_api.json",
        ),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0073_seed_doctor_list_published_by_column"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
