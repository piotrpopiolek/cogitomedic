# Seed intake reopen (REOPENED) choice, reception note fields, domain messages.

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
            "other_domain.json",
        ),
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0070_seed_doctor_pdf_label_signoff_copy"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
