"""Regression: Q4 German question must use Anmerkungen, not PL Uwagi."""

from __future__ import annotations

import importlib

from django.apps import apps
from django.test import TestCase

from apps.intake.models import AnamnesisQuestionDefinition


class Q4GermanNotesLabelTests(TestCase):
    def test_active_q4_de_uses_anmerkungen_not_uwagi(self) -> None:
        questions = AnamnesisQuestionDefinition.objects.filter(
            code="Q4_NEW_SKIN_CHANGES_LOCATION",
            is_active=True,
        )
        self.assertTrue(questions.exists())
        for question in questions:
            self.assertNotIn("Uwagi", question.question_text_de)
            self.assertIn("Anmerkungen", question.question_text_de)

    def test_migration_helper_replaces_uwagi_in_place(self) -> None:
        migration = importlib.import_module(
            "apps.intake.migrations.0027_fix_q4_question_text_de_uwagi"
        )

        q = AnamnesisQuestionDefinition.objects.filter(
            code="Q4_NEW_SKIN_CHANGES_LOCATION"
        ).first()
        self.assertIsNotNone(q)
        assert q is not None
        q.question_text_de = "… bitte im Feld Uwagi angeben (test)"
        q.save(update_fields=["question_text_de"])

        migration.fix_q4_german_notes_label(apps, None)
        q.refresh_from_db()
        self.assertIn("Feld Anmerkungen", q.question_text_de)
        self.assertNotIn("Feld Uwagi", q.question_text_de)

        migration.restore_q4_german_notes_label(apps, None)
        q.refresh_from_db()
        self.assertIn("Feld Uwagi", q.question_text_de)
