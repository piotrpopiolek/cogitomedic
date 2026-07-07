# Pagination page-size selector i18n (doctor + administration).

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
        only_json_filenames=("doctor_ui.json", "administration.json"),
    )
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")
    for category in ("doctor", "administration"):
        TranslationCacheVersion.objects.filter(category=category).update(
            version=F("version") + 1
        )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0111_seed_reception_dashboard_hidrive_i18n_fixes"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
