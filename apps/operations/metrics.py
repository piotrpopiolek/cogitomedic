from __future__ import annotations

from django.db.models import Count, Max, Min, F, Sum, Q
from django.utils import timezone
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client import Gauge

from apps.outbox.models import OutboxEvent, OutboxStatus
from apps.reception.models import PatientImportBatch, PatientImportError

# Typy zdarzeń outbox – używane do emisji serii „zerowych”, żeby metryka zawsze istniała w Prometheusie.
OUTBOX_EVENT_TYPES = ("GENERATE_PDF", "HIDRIVE_UPLOAD", "SMS_SEND")


def build_metrics_payload() -> bytes:
    """Build Prometheus metrics payload for operational checks."""
    registry = CollectorRegistry()

    # 1. Outbox events total (Counter-like, but we use Gauge to set absolute values from DB)
    outbox_events_total = Gauge(
        "cogitomedica_outbox_events_total",
        "Total number of outbox events by type and status.",
        labelnames=["event_type", "status"],
        registry=registry,
    )
    
    # Fast group by query; jeśli brak zdarzeń, emituj przynajmniej jedną serię 0, żeby metryka istniała.
    outbox_counts = list(
        OutboxEvent.objects.values("event_type", "status").annotate(count=Count("id"))
    )
    if outbox_counts:
        for row in outbox_counts:
            outbox_events_total.labels(event_type=row["event_type"], status=row["status"]).set(row["count"])
    else:
        outbox_events_total.labels(event_type="none", status="none").set(0)

    # 2. Oldest pending age (Gauge)
    outbox_pending_age = Gauge(
        "cogitomedica_outbox_pending_age_seconds",
        "Age in seconds of the oldest pending/failed outbox event.",
        labelnames=["event_type"],
        registry=registry,
    )
    
    now = timezone.now()
    # Find oldest created_at for PENDING/FAILED per event_type
    oldest_events = (
        OutboxEvent.objects.filter(status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED])
        .values("event_type")
        .annotate(oldest_created=Min("created_at"))
    )
    for row in oldest_events:
        age_seconds = (now - row["oldest_created"]).total_seconds()
        outbox_pending_age.labels(event_type=row["event_type"]).set(max(0.0, age_seconds))
    if not oldest_events:
        outbox_pending_age.labels(event_type="none").set(0)

    # 3. Processing duration (We provide _sum and _count to allow PromQL to calculate average latency)
    duration_sum = Gauge(
        "cogitomedica_outbox_processing_duration_seconds_sum",
        "Total processing duration in seconds.",
        labelnames=["event_type"],
        registry=registry,
    )
    duration_count = Gauge(
        "cogitomedica_outbox_processing_duration_seconds_count",
        "Total number of processed events for duration calc.",
        labelnames=["event_type"],
        registry=registry,
    )
    
    durations = (
        OutboxEvent.objects.filter(
            status=OutboxStatus.PROCESSED,
            processed_at__isnull=False,
            medical_document_version__published_at__isnull=False,
        )
        .values("event_type")
        .annotate(
            total_time=Sum(F("processed_at") - F("medical_document_version__published_at")),
            count=Count("id")
        )
    )
    for row in durations:
        val_sum = row["total_time"].total_seconds() if row["total_time"] else 0.0
        val_count = row["count"] or 0
        duration_sum.labels(event_type=row["event_type"]).set(val_sum)
        duration_count.labels(event_type=row["event_type"]).set(val_count)
    if not durations:
        for et in OUTBOX_EVENT_TYPES:
            duration_sum.labels(event_type=et).set(0)
            duration_count.labels(event_type=et).set(0)

    # 4. Import batches total
    import_batches_total = Gauge(
        "cogitomedica_import_batches_total",
        "Total number of import batches by status.",
        labelnames=["status"],
        registry=registry,
    )
    batch_counts = list(PatientImportBatch.objects.values("status").annotate(count=Count("id")))
    if batch_counts:
        for row in batch_counts:
            import_batches_total.labels(status=row["status"]).set(row["count"])
    else:
        import_batches_total.labels(status="none").set(0)

    # 5. Import rows total
    import_rows_total = Gauge(
        "cogitomedica_import_rows_total",
        "Total number of imported rows (inserted vs error).",
        labelnames=["status"],
        registry=registry,
    )
    row_stats = PatientImportBatch.objects.aggregate(
        total_inserted=Sum("inserted_rows"),
        total_error=Sum("error_rows")
    )
    import_rows_total.labels(status="inserted").set(row_stats["total_inserted"] or 0)
    import_rows_total.labels(status="error").set(row_stats["total_error"] or 0)

    return generate_latest(registry)
