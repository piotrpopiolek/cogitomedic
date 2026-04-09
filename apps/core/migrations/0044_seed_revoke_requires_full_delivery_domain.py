# Seed other.domain.revoke_requires_full_delivery (HiDrive + SMS before revoke).

from pathlib import Path

from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=("other_domain.json",),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0043_seed_admin_auth_and_app_list_labels"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
