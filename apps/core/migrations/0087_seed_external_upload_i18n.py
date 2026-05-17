# i18n for EXTERNAL_UPLOAD: choices, admin fields, hub button, domain validation copy.

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
            "administration_choices.json",
            "administration_fields.json",
            "administration_templates.json",
            "other_domain.json",
        ),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0086_seed_doctor_paper_intake_modal_cancel"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
