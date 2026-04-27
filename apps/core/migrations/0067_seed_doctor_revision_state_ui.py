from pathlib import Path

from django.conf import settings
from django.db import migrations


def forward(apps, schema_editor):
    """Seed translations for doctor revision-state UX (Stage 5b – Variant B):
    banners (published / in revision), modals (start / discard), confirmation
    messages and the work-queue chip."""
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=("doctor_ui.json", "other_api.json"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0066_seed_doctor_list_scope_filter"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
