# Paper intake: parameterize min-hours-after-appointment in UI/domain strings (no literal "3").

from django.db import migrations

_VALUES: dict[str, dict[str, str]] = {
    "administration.paper_intake_admin_earliest_hint": {
        "de-DE": "Früheste Autorisierungszeit (Termin + {hours} h)",
        "en-GB": "Earliest authorization time (appointment + {hours} h)",
        "pl-PL": "Najwcześniejszy moment autoryzacji (wizyta + {hours} h)",
    },
    "other.domain.paper_intake_authorization_too_early": {
        "de-DE": "Autorisierung frühestens {hours} h nach der Terminzeit möglich.",
        "en-GB": (
            "Authorization is possible only at least {hours} hours after the appointment time."
        ),
        "pl-PL": "Autoryzacja możliwa dopiero po min. {hours} h od godziny wizyty.",
    },
    "other.domain.paper_intake_earliest_after_appointment": {
        "de-DE": (
            "Dokument ohne digitalen Intake kann frühestens {hours} h nach appointment_time "
            "erstellt werden."
        ),
        "en-GB": (
            "Document without digital intake can be created only at least {hours} hours after "
            "appointment_time."
        ),
        "pl-PL": (
            "Dokument bez ankiety cyfrowej można utworzyć dopiero po min. {hours} h po "
            "appointment_time."
        ),
    },
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    for key_str, per_lang in _VALUES.items():
        try:
            key = TranslationKey.objects.get(key=key_str)
        except TranslationKey.DoesNotExist:
            continue
        key.allowed_placeholders = ["hours"]
        key.save(update_fields=["allowed_placeholders"])
        for lang_code, text in per_lang.items():
            TranslationValue.objects.update_or_create(
                translation_key=key,
                language_code=lang_code,
                defaults={"value": text},
            )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0080_seed_paper_intake_hub_list_rules_i18n"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
