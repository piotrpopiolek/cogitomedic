# Seed waiting-room labels for STANDARD / TELEDERM badges.

from pathlib import Path

from django.conf import settings
from django.db import migrations
from django.db.models import F


def forward(apps, schema_editor):
    from apps.core.translation_loader import seed_from_translation_data_directory

    root = Path(settings.BASE_DIR) / "apps" / "core" / "translation_data"
    seed_from_translation_data_directory(
        directory=root,
        apps=apps,
        only_json_filenames=(
            "waiting_room_staff.json",
            "waiting_room_form.json",
        ),
    )
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")
    TranslationCacheVersion.objects.filter(category="waiting_room").update(
        version=F("version") + 1
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0130_seed_process_type_i18n"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
