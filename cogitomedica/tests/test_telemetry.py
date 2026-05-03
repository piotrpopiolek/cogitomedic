"""Tests for optional OpenTelemetry bootstrap (``cogitomedica/telemetry.py``)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


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
    @patch("cogitomedica.telemetry.DjangoInstrumentor")
    @patch("cogitomedica.telemetry.RequestsInstrumentor")
    @patch("cogitomedica.telemetry.PsycopgInstrumentor")
    def test_setup_telemetry_configures_exporter_when_endpoint_set(
        self,
        mock_psycopg_cls: MagicMock,
        mock_requests_cls: MagicMock,
        mock_django_cls: MagicMock,
        mock_set_provider: MagicMock,
        mock_provider_cls: MagicMock,
        mock_exporter_cls: MagicMock,
        mock_processor_cls: MagicMock,
    ) -> None:
        from cogitomedica import telemetry

        mock_django = MagicMock()
        mock_django.is_instrumented_by_opentelemetry = False
        mock_django_cls.return_value = mock_django

        mock_requests = MagicMock()
        mock_requests.is_instrumented_by_opentelemetry = False
        mock_requests_cls.return_value = mock_requests

        mock_psycopg = MagicMock()
        mock_psycopg_cls.return_value = mock_psycopg

        telemetry.setup_telemetry()

        mock_exporter_cls.assert_called_once()
        mock_processor_cls.assert_called_once()
        mock_set_provider.assert_called_once()
        mock_django.instrument.assert_called_once()
        mock_requests.instrument.assert_called_once()
        mock_psycopg.instrument.assert_called_once()

    @patch.dict(
        os.environ,
        {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318/v1/traces"},
    )
    @patch("cogitomedica.telemetry.BatchSpanProcessor")
    @patch("cogitomedica.telemetry.OTLPSpanExporter")
    @patch("cogitomedica.telemetry.TracerProvider")
    @patch("cogitomedica.telemetry.trace.set_tracer_provider")
    @patch("cogitomedica.telemetry.DjangoInstrumentor")
    @patch("cogitomedica.telemetry.RequestsInstrumentor")
    @patch("cogitomedica.telemetry.PsycopgInstrumentor")
    def test_setup_telemetry_skips_second_instrumentation_and_psycopg_failure_is_logged(
        self,
        mock_psycopg_cls: MagicMock,
        mock_requests_cls: MagicMock,
        mock_django_cls: MagicMock,
        _mock_set_provider: MagicMock,
        _mock_provider_cls: MagicMock,
        _mock_exporter_cls: MagicMock,
        _mock_processor_cls: MagicMock,
    ) -> None:
        from cogitomedica import telemetry

        mock_django = MagicMock()
        mock_django.is_instrumented_by_opentelemetry = True
        mock_django_cls.return_value = mock_django

        mock_requests = MagicMock()
        mock_requests.is_instrumented_by_opentelemetry = True
        mock_requests_cls.return_value = mock_requests

        mock_psycopg = MagicMock()
        mock_psycopg.instrument.side_effect = RuntimeError("psycopg already wired")
        mock_psycopg_cls.return_value = mock_psycopg

        telemetry.setup_telemetry()

        mock_django.instrument.assert_not_called()
        mock_requests.instrument.assert_not_called()
        mock_psycopg.instrument.assert_called_once()
