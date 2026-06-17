"""Unit tests for apps/intake/tasks.py — verifies each task delegates to the right service."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings


class ProcessIntakeOutboxEventsTaskTests(TestCase):
    @patch("apps.intake.tasks.process_intake_outbox_events_service")
    def test_task_calls_outbox_service_once(self, mock_svc) -> None:
        from apps.intake.tasks import process_intake_outbox_events

        process_intake_outbox_events.call()
        mock_svc.assert_called_once_with()

    @patch("apps.intake.tasks.process_intake_outbox_events_service")
    def test_task_passes_no_arguments_to_service(self, mock_svc) -> None:
        from apps.intake.tasks import process_intake_outbox_events

        process_intake_outbox_events.call()
        args, kwargs = mock_svc.call_args
        self.assertEqual(args, ())
        self.assertEqual(kwargs, {})


class RunIntakeRetentionCleanupTaskTests(TestCase):
    @override_settings(PDF_RETENTION_DAYS=60)
    @patch("apps.intake.tasks.run_intake_retention_cleanup_service")
    def test_task_calls_retention_service_with_settings_days(self, mock_svc) -> None:
        from apps.intake.tasks import run_intake_retention_cleanup

        run_intake_retention_cleanup.call()
        mock_svc.assert_called_once_with(older_than_days=60, dry_run=False)

    @override_settings(PDF_RETENTION_DAYS=90)
    @patch("apps.intake.tasks.run_intake_retention_cleanup_service")
    def test_task_reads_pdf_retention_days_from_settings(self, mock_svc) -> None:
        from apps.intake.tasks import run_intake_retention_cleanup

        run_intake_retention_cleanup.call()
        mock_svc.assert_called_once_with(older_than_days=90, dry_run=False)

    @override_settings(PDF_RETENTION_DAYS=60)
    @patch("apps.intake.tasks.run_intake_retention_cleanup_service")
    def test_task_always_runs_with_dry_run_false(self, mock_svc) -> None:
        from apps.intake.tasks import run_intake_retention_cleanup

        run_intake_retention_cleanup.call()
        _, kwargs = mock_svc.call_args
        self.assertFalse(kwargs["dry_run"])
