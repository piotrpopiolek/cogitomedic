import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

logger = logging.getLogger(__name__)


def _django_instrumentor_cls():
    """Return ``DjangoInstrumentor`` class (indirection for tests via ``patch``)."""
    from opentelemetry.instrumentation.django import DjangoInstrumentor

    return DjangoInstrumentor


def _requests_instrumentor_cls():
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    return RequestsInstrumentor


def _psycopg_instrumentor_cls():
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    return PsycopgInstrumentor


def setup_telemetry():
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        service_name = os.environ.get("OTEL_SERVICE_NAME", "cogitomedica-unknown")

        resource = Resource(attributes={ResourceAttributes.SERVICE_NAME: service_name})

        provider = TracerProvider(resource=resource)

        # Używamy HTTP expoter do OTLP, domyślny port dla OTLP/HTTP to 4318
        # Endpoint to zazwyczaj format: http://otel-collector:4318/v1/traces
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

        exporter = OTLPSpanExporter(endpoint=endpoint)

        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        # Auto-instrumentacje (class lookups via module-level helpers so tests can patch
        # ``cogitomedica.telemetry._*_instrumentor_cls`` reliably).
        dj_cls = _django_instrumentor_cls()
        if not dj_cls().is_instrumented_by_opentelemetry:
            dj_cls().instrument()
        rq_cls = _requests_instrumentor_cls()
        if not rq_cls().is_instrumented_by_opentelemetry:
            rq_cls().instrument()
        pg_cls = _psycopg_instrumentor_cls()
        if not pg_cls().is_instrumented_by_opentelemetry:
            try:
                pg_cls().instrument(enable_commenter=True, commenter_options={})
            except Exception:
                logger.warning(
                    "OpenTelemetry Psycopg instrumentation skipped (e.g. DB already "
                    "connected or incompatible psycopg version).",
                    exc_info=True,
                )
