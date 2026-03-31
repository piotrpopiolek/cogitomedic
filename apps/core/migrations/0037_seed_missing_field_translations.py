# Seed missing administration.field_anonymization_started_at,
# administration.field_anonymized_at, administration.field_consent_summary.

from pathlib import Path

from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=("administration_fields.json",),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_seed_administration_templates"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
