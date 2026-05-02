import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

logger = logging.getLogger(__name__)


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

        # Auto-instrumentacje
        if not DjangoInstrumentor().is_instrumented_by_opentelemetry:
            DjangoInstrumentor().instrument()
        if not RequestsInstrumentor().is_instrumented_by_opentelemetry:
            RequestsInstrumentor().instrument()
        if not PsycopgInstrumentor().is_instrumented_by_opentelemetry:
            try:
                PsycopgInstrumentor().instrument(
                    enable_commenter=True, commenter_options={}
                )
            except Exception:
                logger.warning(
                    "OpenTelemetry Psycopg instrumentation skipped (e.g. DB already "
                    "connected or incompatible psycopg version).",
                    exc_info=True,
                )
