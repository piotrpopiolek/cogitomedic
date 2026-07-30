"""Prometheus alerts.yml — outbox / dead-letter rules."""

from __future__ import annotations

from pathlib import Path

import yaml
from django.test import SimpleTestCase

_ALERTS_PATH = Path(__file__).resolve().parents[1] / "alerts.yml"
_PROMTOOL_TEST_PATH = (
    Path(__file__).resolve().parent / "outbox_dead_letter_alert_test.yml"
)


def _alert_rules_by_name() -> dict[str, dict]:
    data = yaml.safe_load(_ALERTS_PATH.read_text(encoding="utf-8"))
    rules: dict[str, dict] = {}
    for group in data["groups"]:
        for rule in group.get("rules", []):
            name = rule.get("alert")
            if name:
                rules[name] = rule
    return rules


class OutboxDeadLetterAlertTests(SimpleTestCase):
    def test_outbox_dead_letter_alert_defined(self) -> None:
        rules = _alert_rules_by_name()
        self.assertIn("OutboxDeadLetterPresent", rules)
        self.assertIn("OutboxBacklogTooOld", rules)

    def test_outbox_dead_letter_expr_covers_medical_and_intake(self) -> None:
        expr = _alert_rules_by_name()["OutboxDeadLetterPresent"]["expr"]
        self.assertIn('cogitomedica_outbox_events_total{status="DEAD_LETTER"}', expr)
        self.assertIn(
            'cogitomedica_intake_outbox_events_total{status="DEAD_LETTER"}', expr
        )
        self.assertIn(" > 0", expr)

    def test_outbox_dead_letter_severity_and_for(self) -> None:
        rule = _alert_rules_by_name()["OutboxDeadLetterPresent"]
        self.assertEqual(rule["labels"]["severity"], "critical")
        self.assertEqual(rule["for"], "5m")
        self.assertIn("OUTBOX_BACKLOG_AGE", rule["annotations"]["description"])

    def test_backlog_too_old_annotation_mentions_dead_letter_gap(self) -> None:
        desc = _alert_rules_by_name()["OutboxBacklogTooOld"]["annotations"][
            "description"
        ]
        self.assertIn("OutboxDeadLetterPresent", desc)

    def test_promtool_unit_test_file_exists_and_references_alert(self) -> None:
        self.assertTrue(_PROMTOOL_TEST_PATH.is_file())
        body = _PROMTOOL_TEST_PATH.read_text(encoding="utf-8")
        self.assertIn("OutboxDeadLetterPresent", body)
        self.assertIn("alerts.yml", body)
