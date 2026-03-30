"""Tests for management commands in apps/core."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.core.models import TranslationKey, TranslationValue


class LoadDefaultTranslationsCommandTests(TestCase):
    """load_default_translations loads JSON seed data idempotently."""

    def test_command_runs_without_error(self) -> None:
        out = StringIO()
        call_command("load_default_translations", stdout=out)
        output = out.getvalue()
        self.assertIn("finished", output.lower())

    def test_command_creates_translation_keys(self) -> None:
        call_command("load_default_translations", stdout=StringIO())
        self.assertGreater(TranslationKey.objects.count(), 0)

    def test_command_creates_translation_values(self) -> None:
        call_command("load_default_translations", stdout=StringIO())
        self.assertGreater(TranslationValue.objects.count(), 0)

    def test_command_is_idempotent(self) -> None:
        """Running the command twice should not raise and should not duplicate keys."""
        out1 = StringIO()
        call_command("load_default_translations", stdout=out1)
        count_after_first = TranslationKey.objects.count()

        out2 = StringIO()
        call_command("load_default_translations", stdout=out2)
        count_after_second = TranslationKey.objects.count()

        self.assertEqual(count_after_first, count_after_second)
        # Second run should report 0 new rows
        self.assertIn("0", out2.getvalue())

    def test_check_translations_completeness_passes_after_load(self) -> None:
        """After loading, the completeness check should not raise CommandError."""
        call_command("load_default_translations", stdout=StringIO())
        out = StringIO()
        call_command("check_translations_completeness", stdout=out)
        self.assertIn("passed", out.getvalue().lower())
