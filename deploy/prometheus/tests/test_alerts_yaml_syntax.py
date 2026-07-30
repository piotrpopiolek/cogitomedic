"""Prometheus alerts.yml loads and contains disk threshold rules."""

from __future__ import annotations

from pathlib import Path

import yaml
from django.test import SimpleTestCase

_ALERTS_PATH = Path(__file__).resolve().parents[1] / "alerts.yml"


class PrometheusAlertsYamlTests(SimpleTestCase):
    def test_alerts_yaml_parses(self) -> None:
        data = yaml.safe_load(_ALERTS_PATH.read_text(encoding="utf-8"))
        self.assertIn("groups", data)
        group_names = [g["name"] for g in data["groups"]]
        self.assertIn("cogitomedica_host_disk_alerts", group_names)

    def test_disk_usage_threshold_alerts_defined(self) -> None:
        data = yaml.safe_load(_ALERTS_PATH.read_text(encoding="utf-8"))
        alert_names: set[str] = set()
        for group in data["groups"]:
            for rule in group.get("rules", []):
                if "alert" in rule:
                    alert_names.add(rule["alert"])
        for threshold in (50, 60, 70, 80, 90):
            self.assertIn(f"DiskUsageAbove{threshold}Percent", alert_names)
        self.assertIn("OutboxDeadLetterPresent", alert_names)
        self.assertIn("OutboxBacklogTooOld", alert_names)
