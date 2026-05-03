"""Tests for optional OpenTelemetry bootstrap (``cogitomedica/telemetry.py``)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


def _instrumentor_class_mock(*, instrumented: bool) -> MagicMock:
    """Return a mock *class* whose ``()`` yields an instance with the given flag."""
    inst = MagicMock()
    inst.configure_mock(**{"is_instrumented_by_opentelemetry": instrumented})
    return MagicMock(return_value=inst)


class SetupTelemetryTests(SimpleTestCase):
    def test_setup_telemetry_is_noop_without_otel_endpoint(self) -> None:
        from cogitomedica import telemetry

        with patch.dict(os.environ, {}, clear=True):
            telemetry.setup_telemetry()

    @patch.dict(
        os.environ,
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318/v1/traces",
            "OTEL_SERVICE_NAME": "cogitomedica-test",
        },
    )
    @patch("cogitomedica.telemetry.BatchSpanProcessor")
    @patch("cogitomedica.telemetry.OTLPSpanExporter")
    @patch("cogitomedica.telemetry.TracerProvider")
    @patch("cogitomedica.telemetry.trace.set_tracer_provider")
    @patch("cogitomedica.telemetry._psycopg_instrumentor_cls")
    @patch("cogitomedica.telemetry._requests_instrumentor_cls")
    @patch("cogitomedica.telemetry._django_instrumentor_cls")
    def test_setup_telemetry_configures_exporter_when_endpoint_set(
        self,
        mock_django_factory: MagicMock,
        mock_requests_factory: MagicMock,
        mock_psycopg_factory: MagicMock,
        mock_set_provider: MagicMock,
        mock_provider_cls: MagicMock,
        mock_exporter_cls: MagicMock,
        mock_processor_cls: MagicMock,
    ) -> None:
        from cogitomedica import telemetry

        mock_django_factory.return_value = _instrumentor_class_mock(instrumented=False)
        mock_requests_factory.return_value = _instrumentor_class_mock(
            instrumented=False
        )
        mock_psycopg_factory.return_value = _instrumentor_class_mock(instrumented=False)

        telemetry.setup_telemetry()

        mock_exporter_cls.assert_called_once()
        mock_processor_cls.assert_called_once()
        mock_set_provider.assert_called_once()
        dj_cls = mock_django_factory.return_value
        rq_cls = mock_requests_factory.return_value
        pg_cls = mock_psycopg_factory.return_value
        dj_cls.return_value.instrument.assert_called_once()
        rq_cls.return_value.instrument.assert_called_once()
        pg_cls.return_value.instrument.assert_called_once()

    @patch.dict(
        os.environ,
        {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318/v1/traces"},
    )
    @patch("cogitomedica.telemetry.BatchSpanProcessor")
    @patch("cogitomedica.telemetry.OTLPSpanExporter")
    @patch("cogitomedica.telemetry.TracerProvider")
    @patch("cogitomedica.telemetry.trace.set_tracer_provider")
    @patch("cogitomedica.telemetry._psycopg_instrumentor_cls")
    @patch("cogitomedica.telemetry._requests_instrumentor_cls")
    @patch("cogitomedica.telemetry._django_instrumentor_cls")
    def test_setup_telemetry_skips_second_instrumentation_and_psycopg_failure_is_logged(
        self,
        mock_django_factory: MagicMock,
        mock_requests_factory: MagicMock,
        mock_psycopg_factory: MagicMock,
        _mock_set_provider: MagicMock,
        _mock_provider_cls: MagicMock,
        _mock_exporter_cls: MagicMock,
        _mock_processor_cls: MagicMock,
    ) -> None:
        from cogitomedica import telemetry

        mock_django_factory.return_value = _instrumentor_class_mock(instrumented=True)
        mock_requests_factory.return_value = _instrumentor_class_mock(instrumented=True)
        pg_inst = MagicMock()
        pg_inst.configure_mock(**{"is_instrumented_by_opentelemetry": False})
        pg_inst.instrument.side_effect = RuntimeError("psycopg already wired")
        mock_psycopg_factory.return_value = MagicMock(return_value=pg_inst)

        telemetry.setup_telemetry()

        mock_django_factory.return_value.return_value.instrument.assert_not_called()
        mock_requests_factory.return_value.return_value.instrument.assert_not_called()
        pg_inst.instrument.assert_called_once()
