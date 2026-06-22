# Update existing body_map_hint values (seed only creates new TranslationValue rows).

from django.db import migrations
from django.db.models import F

_VALUES: dict[str, dict[str, str]] = {
    "waiting_room.form.body_map_hint": {
        "de-DE": (
            "Bitte markieren Sie auf dem Körperschema die Hautveränderungen, "
            "die Ihnen besonders auffällig oder besorgniserregend erscheinen."
        ),
        "en-GB": (
            "Please mark on the body diagram which skin changes are of "
            "particular concern to you."
        ),
        "pl-PL": (
            "Proszę zaznaczyć na schemacie ciała, które zmiany skórne "
            "szczególnie Pana/Panią niepokoją."
        ),
    },
    "waiting_room.form.body_map_hint_technical": {
        "de-DE": (
            "Tippen Sie auf die Abbildung, um einen Punkt zu setzen. "
            "Links: Vorderansicht, rechts: Rückansicht."
        ),
        "en-GB": "Tap on the figure to place a point. Left: front, right: back.",
        "pl-PL": "Dotknij rysunku, aby ustawić punkt. Lewy: przód, prawy: tył.",
    },
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")

    for key_str, per_lang in _VALUES.items():
        try:
            key = TranslationKey.objects.get(key=key_str)
        except TranslationKey.DoesNotExist:
            continue
        for lang_code, text in per_lang.items():
            TranslationValue.objects.update_or_create(
                translation_key=key,
                language_code=lang_code,
                defaults={"value": text},
            )

    TranslationCacheVersion.objects.filter(category="waiting_room").update(
        version=F("version") + 1
    )


def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    TranslationCacheVersion = apps.get_model("core", "TranslationCacheVersion")

    old_hint = {
        "de-DE": (
            "Tippen Sie auf die Abbildung, um die Lage von Hautveränderungen "
            "(z. B. Muttermale) zu markieren. Links: Vorderansicht, rechts: Rückansicht."
        ),
        "en-GB": (
            "Tap on the figure to mark the location of skin changes (e.g. moles). "
            "Left: front, right: back."
        ),
        "pl-PL": (
            "Dotknij rysunku, aby zaznaczyć lokalizację zmian skórnych (np. znamion). "
            "Lewy: przód, prawy: tył."
        ),
    }
    try:
        key = TranslationKey.objects.get(key="waiting_room.form.body_map_hint")
    except TranslationKey.DoesNotExist:
        key = None
    if key is not None:
        for lang_code, text in old_hint.items():
            TranslationValue.objects.filter(
                translation_key=key,
                language_code=lang_code,
            ).update(value=text)

    try:
        technical_key = TranslationKey.objects.get(
            key="waiting_room.form.body_map_hint_technical"
        )
    except TranslationKey.DoesNotExist:
        technical_key = None
    if technical_key is not None:
        TranslationValue.objects.filter(translation_key=technical_key).delete()
        if not TranslationValue.objects.filter(translation_key=technical_key).exists():
            technical_key.delete()

    TranslationCacheVersion.objects.filter(category="waiting_room").update(
        version=F("version") + 1
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0106_seed_body_map_hint_instruction"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
