# Generated manually – seed doctor validation messages (publish requirements)

from django.db import migrations

VALIDATION_MESSAGES = {
    "doctor.msg_validation_examination_scope_required": {
        "de": "Vor der Veröffentlichung muss die Sektion „1. Untersuchungsumfang (Mehrfachauswahl)“ ausgefüllt werden: mindestens eine Option ankreuzen (Intimbereich nicht untersucht oder Mundschleimhaut nicht untersucht).",
        "en": "Before publishing, please fill in section \"1. Scope of examination (multiple choice)\": select at least one option (Intimate area not examined or Oral mucosa not examined).",
        "pl": "Przed publikacją należy wypełnić sekcję „1. Untersuchungsumfang (Mehrfachauswahl)”: zaznacz co najmniej jedną opcję (Intimbereich nicht untersucht lub Mundschleimhaut nicht untersucht).",
    },
    "doctor.msg_validation_fitzpatrick_required": {
        "de": "Vor der Veröffentlichung muss der Hauttyp nach Fitzpatrick (Sektion 2) gewählt werden.",
        "en": "Before publishing, please select Fitzpatrick skin type (section 2).",
        "pl": "Przed publikacją należy wybrać Hauttyp nach Fitzpatrick (sekcja 2).",
    },
    "doctor.msg_validation_overall_assessment_required": {
        "de": "Vor der Veröffentlichung muss die Gesamtbeurteilung der Bildanalyse (Sektion 3) gewählt werden.",
        "en": "Before publishing, please select overall image assessment (section 3).",
        "pl": "Przed publikacją należy wybrać ocenę ogólną analizy obrazu (sekcja 3).",
    },
    "doctor.msg_validation_recommendations_required": {
        "de": "Vor der Veröffentlichung muss mindestens eine ärztliche Empfehlung (Sektion 10) ausgewählt werden.",
        "en": "Before publishing, please select at least one medical recommendation (section 10).",
        "pl": "Przed publikacją należy wybrać co najmniej jedną zalecenie lekarskie (sekcja 10).",
    },
    "doctor.msg_validation_final_assessment_required": {
        "de": "Vor der Veröffentlichung muss die ärztliche Gesamteinschätzung (Sektion 11) gewählt werden.",
        "en": "Before publishing, please select final medical assessment (section 11).",
        "pl": "Przed publikacją należy wybrać końcową ocenę lekarską (sekcja 11).",
    },
}


def forward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    TranslationValue = apps.get_model("core", "TranslationValue")
    for full_key, lang_to_value in VALIDATION_MESSAGES.items():
        key, _ = TranslationKey.objects.get_or_create(
            key=full_key,
            defaults={
                "category": "doctor",
                "description": "Doctor UI – validation message before publish",
                "is_html_allowed": False,
                "allowed_placeholders": [],
                "status": "ACTIVE",
            },
        )
        for lang, text in lang_to_value.items():
            TranslationValue.objects.update_or_create(
                translation_key=key,
                language_code=lang,
                defaults={"value": text},
            )


def backward(apps, schema_editor):
    TranslationKey = apps.get_model("core", "TranslationKey")
    keys_to_remove = list(VALIDATION_MESSAGES.keys())
    TranslationKey.objects.filter(key__in=keys_to_remove).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_alter_translationcacheversion_language_code_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
