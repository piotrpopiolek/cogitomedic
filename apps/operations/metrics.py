from __future__ import annotations

from django.utils import timezone
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from apps.outbox.models import OutboxEvent, OutboxStatus


def build_metrics_payload() -> bytes:
    """Build Prometheus metrics payload for operational checks."""
    registry = CollectorRegistry()

    pending_count_gauge = Gauge(
        "cogitomedica_outbox_pending_count",
        "Number of pending outbox events.",
        registry=registry,
    )
    failed_count_gauge = Gauge(
        "cogitomedica_outbox_failed_count",
        "Number of failed outbox events.",
        registry=registry,
    )
    dead_letter_count_gauge = Gauge(
        "cogitomedica_outbox_dead_letter_count",
        "Number of dead-letter outbox events.",
        registry=registry,
    )
    oldest_pending_age_gauge = Gauge(
        "cogitomedica_outbox_oldest_pending_age_seconds",
        "Age in seconds of the oldest pending/failed outbox event.",
        registry=registry,
    )

    pending_count = OutboxEvent.objects.filter(status=OutboxStatus.PENDING).count()
    failed_count = OutboxEvent.objects.filter(status=OutboxStatus.FAILED).count()
    dead_letter_count = OutboxEvent.objects.filter(status=OutboxStatus.DEAD_LETTER).count()

    pending_count_gauge.set(pending_count)
    failed_count_gauge.set(failed_count)
    dead_letter_count_gauge.set(dead_letter_count)

    oldest_event = (
        OutboxEvent.objects.filter(status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED])
        .order_by("created_at")
        .first()
    )
    if oldest_event is None:
        oldest_pending_age_gauge.set(0)
    else:
        oldest_pending_age_gauge.set((timezone.now() - oldest_event.created_at).total_seconds())

    return generate_latest(registry)
