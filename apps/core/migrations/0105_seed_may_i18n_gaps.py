# Close May i18n gaps: paper intake doctor UI, external upload publish id, fields, domain.error.

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
            "doctor_ui.json",
            "administration.json",
            "administration_fields.json",
            "other_domain.json",
        ),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0104_seed_shared_phone_portal_and_api_strings"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
