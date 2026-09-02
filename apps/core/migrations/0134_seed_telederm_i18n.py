# Seed telederm i18n keys (tablet form, doctor panel, domain messages).

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
            "other_domain.json",
            "waiting_room_form.json",
            "doctor_ui.json",
        ),
    )
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")
    for category in ("other", "waiting_room", "doctor"):
        TranslationCacheVersion.objects.filter(category=category).update(
            version=F("version") + 1
        )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0133_seed_import_process_type_i18n"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
