"""Coverage for apps.operations.prom_metrics ORM collector (diff-cover)."""

from __future__ import annotations

import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from apps.intake.models import IntakeOutboxEvent
from apps.outbox.models import OutboxEvent
from apps.reception.models import PatientImportBatch, PatientImportError

from apps.operations.prom_metrics import _OrmMetricsCollector, build_metrics_payload


def _purge_seed_clinic_data() -> None:
    mod = importlib.import_module(
        "apps.reception.migrations.0030_purge_seed_clinics_demo_muc"
    )
    mod.purge_seed_clinic_data(django_apps)


def _collect_all() -> list:
    return list(_OrmMetricsCollector().collect())


class OrmMetricsCollectorEmptyTablesTests(TestCase):
    """Hit `else` branches (none / zero placeholders) when ORM aggregates are empty."""

    def setUp(self) -> None:
        _purge_seed_clinic_data()
        OutboxEvent.objects.all().delete()
        IntakeOutboxEvent.objects.all().delete()
        PatientImportError.objects.all().delete()
        PatientImportBatch.objects.all().delete()

    def test_collect_with_empty_outbox_intake_import_tables(self) -> None:
        families = _collect_all()
        names = {f.name for f in families}
        self.assertIn("cogitomedica_outbox_events_total", names)
        self.assertIn("cogitomedica_intake_outbox_events_total", names)
        self.assertIn("cogitomedica_import_batches_total", names)
        self.assertIn("cogitomedica_active_users", names)
        self.assertIn("cogitomedica_doctors_editing", names)

    def test_build_metrics_payload_second_call_returns_bytes(self) -> None:
        first = build_metrics_payload()
        second = build_metrics_payload()
        self.assertIsInstance(first, bytes)
        self.assertIsInstance(second, bytes)
        self.assertGreater(len(second), 0)
