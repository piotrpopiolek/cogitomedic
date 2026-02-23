from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from prometheus_client import CollectorRegistry, Gauge, generate_latest

from apps.outbox.models import OutboxEventType
from apps.outbox.models import OutboxEvent, OutboxStatus


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int((len(sorted_values) - 1) * p)
    return float(sorted_values[idx])


def _success_ratio_for_event(event_type: str, window_hours: int = 1) -> float:
    start = timezone.now() - timedelta(hours=window_hours)
    qs = OutboxEvent.objects.filter(
        event_type=event_type,
        created_at__gte=start,
        status__in=[OutboxStatus.PROCESSED, OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER],
    )
    total = qs.count()
    if total == 0:
        return 1.0
    processed = qs.filter(status=OutboxStatus.PROCESSED).count()
    return processed / total


def _publish_to_stage_latencies(event_type: str, window_hours: int = 24) -> list[float]:
    start = timezone.now() - timedelta(hours=window_hours)
    events = (
        OutboxEvent.objects.select_related("medical_document_version")
        .filter(
            event_type=event_type,
            status=OutboxStatus.PROCESSED,
            processed_at__isnull=False,
            processed_at__gte=start,
            medical_document_version__published_at__isnull=False,
        )
        .only("processed_at", "medical_document_version__published_at")
    )
    latencies: list[float] = []
    for event in events:
        published_at = event.medical_document_version.published_at
        if published_at is None or event.processed_at is None:
            continue
        latency = (event.processed_at - published_at).total_seconds()
        if latency >= 0:
            latencies.append(latency)
    return latencies


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
    pdf_success_ratio_1h_gauge = Gauge(
        "cogitomedica_pdf_success_ratio_1h",
        "Success ratio for GENERATE_PDF events in last 1h.",
        registry=registry,
    )
    hidrive_success_ratio_1h_gauge = Gauge(
        "cogitomedica_hidrive_success_ratio_1h",
        "Success ratio for HIDRIVE_UPLOAD events in last 1h.",
        registry=registry,
    )
    sms_success_ratio_1h_gauge = Gauge(
        "cogitomedica_sms_success_ratio_1h",
        "Success ratio for SMS_SEND events in last 1h.",
        registry=registry,
    )
    publish_to_pdf_p95 = Gauge(
        "cogitomedica_publish_to_pdf_latency_p95_seconds",
        "P95 latency from publish to PDF processed.",
        registry=registry,
    )
    publish_to_hidrive_p95 = Gauge(
        "cogitomedica_publish_to_hidrive_latency_p95_seconds",
        "P95 latency from publish to HiDrive processed.",
        registry=registry,
    )
    publish_to_sms_p95 = Gauge(
        "cogitomedica_publish_to_sms_latency_p95_seconds",
        "P95 latency from publish to SMS processed.",
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

    pdf_success_ratio_1h_gauge.set(_success_ratio_for_event(OutboxEventType.GENERATE_PDF))
    hidrive_success_ratio_1h_gauge.set(_success_ratio_for_event(OutboxEventType.HIDRIVE_UPLOAD))
    sms_success_ratio_1h_gauge.set(_success_ratio_for_event(OutboxEventType.SMS_SEND))

    publish_to_pdf_p95.set(_percentile(_publish_to_stage_latencies(OutboxEventType.GENERATE_PDF), 0.95))
    publish_to_hidrive_p95.set(_percentile(_publish_to_stage_latencies(OutboxEventType.HIDRIVE_UPLOAD), 0.95))
    publish_to_sms_p95.set(_percentile(_publish_to_stage_latencies(OutboxEventType.SMS_SEND), 0.95))

    return generate_latest(registry)
