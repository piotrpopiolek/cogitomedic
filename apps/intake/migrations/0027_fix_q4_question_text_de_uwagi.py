"""Replace PL „Uwagi” in German Q4 anamnesis question with „Anmerkungen”."""

from django.db import migrations

_OLD_SNIPPET = "Feld Uwagi"
_NEW_SNIPPET = "Feld Anmerkungen"
_QUESTION_CODE = "Q4_NEW_SKIN_CHANGES_LOCATION"


def fix_q4_german_notes_label(apps, schema_editor):
    AnamnesisQuestionDefinition = apps.get_model(
        "intake", "AnamnesisQuestionDefinition"
    )
    for question in AnamnesisQuestionDefinition.objects.filter(
        code=_QUESTION_CODE,
        question_text_de__contains=_OLD_SNIPPET,
    ):
        question.question_text_de = question.question_text_de.replace(
            _OLD_SNIPPET, _NEW_SNIPPET
        )
        question.save(update_fields=["question_text_de"])


def restore_q4_german_notes_label(apps, schema_editor):
    AnamnesisQuestionDefinition = apps.get_model(
        "intake", "AnamnesisQuestionDefinition"
    )
    for question in AnamnesisQuestionDefinition.objects.filter(
        code=_QUESTION_CODE,
        question_text_de__contains=_NEW_SNIPPET,
    ):
        question.question_text_de = question.question_text_de.replace(
            _NEW_SNIPPET, _OLD_SNIPPET
        )
        question.save(update_fields=["question_text_de"])


class Migration(migrations.Migration):

    dependencies = [
        ("intake", "0026_intakeoutbox_max_retries_default_3"),
    ]

    operations = [
        migrations.RunPython(fix_q4_german_notes_label, restore_q4_german_notes_label),
    ]
