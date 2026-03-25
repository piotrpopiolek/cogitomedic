# Seed REST API error strings (other.api.*) and admin enum choice labels (administration.choice_*).

from pathlib import Path

from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=("other_api.json", "administration_choices.json"),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_seed_administration_fields_json"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
