"""Tests for scheduler Prometheus metrics HTTP server."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.operations.metrics_server import (
    _MetricsHandler,
    _bearer_authorized,
    build_runtime_metrics_payload,
)
from apps.operations.prom_metrics import build_metrics_payload, record_outbox_execution


class BearerAuthTests(SimpleTestCase):
    @override_settings(PROMETHEUS_METRICS_TOKEN="secret-token")
    def test_accepts_matching_bearer(self) -> None:
        self.assertTrue(_bearer_authorized("Bearer secret-token"))

    @override_settings(PROMETHEUS_METRICS_TOKEN="secret-token")
    def test_rejects_wrong_token(self) -> None:
        self.assertFalse(_bearer_authorized("Bearer other-token"))

    @override_settings(PROMETHEUS_METRICS_TOKEN="secret-token")
    def test_rejects_missing_header(self) -> None:
        self.assertFalse(_bearer_authorized(None))

    @override_settings(PROMETHEUS_METRICS_TOKEN=None)
    def test_rejects_when_token_unset(self) -> None:
        self.assertFalse(_bearer_authorized("Bearer anything"))


class RuntimeMetricsPayloadTests(SimpleTestCase):
    def test_payload_includes_counter_after_record(self) -> None:
        now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
        record_outbox_execution(
            stream="befund",
            event_type="SMS_SEND",
            result="success",
            start_ts=now,
            end_ts=now,
        )
        payload = build_runtime_metrics_payload().decode("utf-8")
        self.assertIn("cogitomedica_outbox_executions_total", payload)
        self.assertIn('event_type="SMS_SEND"', payload)
        self.assertNotIn("cogitomedica_outbox_events_total", payload)


class RuntimeMetricsIgnoresOrmCollectorTests(TestCase):
    """After web scrape registers ORM gauges on the shared registry, runtime export must stay DB-free of gauges."""

    def test_runtime_payload_excludes_orm_gauges_after_full_payload(self) -> None:
        build_metrics_payload()
        now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
        record_outbox_execution(
            stream="befund",
            event_type="HIDRIVE_UPLOAD",
            result="success",
            start_ts=now,
            end_ts=now,
        )
        payload = build_runtime_metrics_payload().decode("utf-8")
        self.assertIn("cogitomedica_outbox_executions_total", payload)
        self.assertIn('event_type="HIDRIVE_UPLOAD"', payload)
        self.assertNotIn("cogitomedica_outbox_events_total", payload)


class MetricsHandlerTests(SimpleTestCase):
    @override_settings(PROMETHEUS_METRICS_TOKEN="tok")
    def test_get_metrics_ok(self) -> None:
        handler = mock.Mock(spec=_MetricsHandler)
        handler.path = "/api/v1/observability/metrics"
        handler.headers = {"Authorization": "Bearer tok"}
        handler.wfile = mock.Mock()
        _MetricsHandler.do_GET(handler)
        handler.send_response.assert_called_with(200)

    @override_settings(PROMETHEUS_METRICS_TOKEN="tok")
    def test_get_metrics_unauthorized(self) -> None:
        handler = mock.Mock(spec=_MetricsHandler)
        handler.path = "/api/v1/observability/metrics"
        handler.headers = {"Authorization": "Bearer wrong"}
        handler.wfile = mock.Mock()
        _MetricsHandler.do_GET(handler)
        handler.send_response.assert_called_with(401)
