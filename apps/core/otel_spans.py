"""OpenTelemetry helpers for domain-level spans (business attributes)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.trace import Span

from apps.core.exceptions import DomainError

tracer = trace.get_tracer("cogitomedica.domain")


@contextmanager
def cogito_business_span(
    name: str,
    *,
    queue_entry_id: uuid.UUID | None = None,
    audit_event_type: str | None = None,
    extra_attributes: dict[str, Any] | None = None,
) -> Iterator[Span]:
    """Span for state transitions; does not record DomainError as an exception."""
    attrs: dict[str, Any] = {}
    if queue_entry_id is not None:
        attrs["cogito.queue_entry_id"] = str(queue_entry_id)
    if audit_event_type is not None:
        attrs["cogito.audit_event_type"] = audit_event_type
    if extra_attributes:
        attrs.update(extra_attributes)
    with tracer.start_as_current_span(name, attributes=attrs) as span:
        try:
            yield span
        except Exception as e:
            if span.is_recording() and not isinstance(e, DomainError):
                span.record_exception(e)
            raise
