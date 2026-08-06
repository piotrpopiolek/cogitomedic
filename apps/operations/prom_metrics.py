"""
Prometheus metrics: ORM snapshot collector + runtime Counters/Histograms.

Runtime counters are incremented when workers complete outbox steps (correct semantics
for rate() / increase() in Prometheus). With ImmediateBackend those workers run in the
**scheduler** process — scrape job ``cogitomedica_scheduler`` (port SCHEDULER_METRICS_PORT).
ORM-derived Gauges are exported from ``web`` (``build_metrics_payload``); the scheduler
endpoint exports runtime metrics only (``build_runtime_metrics_payload``).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily

if TYPE_CHECKING:
    from datetime import datetime

_registry = CollectorRegistry()
_lock = threading.Lock()
_components_registered = False

OUTBOX_EVENT_TYPES = ("GENERATE_PDF", "HIDRIVE_UPLOAD", "SMS_SEND")
INTAKE_OUTBOX_EVENT_TYPES = ("GENERATE_INTAKE_PDF", "HIDRIVE_UPLOAD_INTAKE_PDF")

# Usage gauges (ORM scrape on web) — counts only, no PHI / no user ids in labels.
ACTIVE_USER_WINDOWS_MINUTES: tuple[tuple[str, int], ...] = (("15m", 15), ("60m", 60))
PATIENT_PORTAL_ACTIVITY_EVENT_TYPES: tuple[str, ...] = (
    "PATIENT_RESULTS_OTP_VERIFY",
    "PATIENT_RESULTS_DOCUMENTS_LISTED",
    "PATIENT_RESULTS_PDF_DOWNLOAD",
)

OUTBOX_EXECUTIONS = Counter(
    "cogitomedica_outbox_executions_total",
    "Outbox worker completions (success, failed, dead_letter) per stream and event type.",
    labelnames=["stream", "event_type", "result"],
    registry=_registry,
)

OUTBOX_PUBLISH_TO_PROCESSED = Histogram(
    "cogitomedica_outbox_publish_to_processed_seconds",
    "Seconds from medical published_at (befund) or intake version created_at (intake) "
    "to outbox processed_at; observed only on success.",
    labelnames=["stream", "event_type"],
    buckets=(
        0.5,
        1,
        2,
        5,
        10,
        30,
        60,
        120,
        300,
        600,
        1800,
        3600,
    ),
    registry=_registry,
)

IMPORT_BATCHES_COMPLETED = Counter(
    "cogitomedica_import_batches_completed_total",
    "Patient XLSX import batches finished (by outcome).",
    labelnames=["result"],
    registry=_registry,
)

IMPORT_BATCH_DURATION = Histogram(
    "cogitomedica_import_batch_duration_seconds",
    "Wall time from batch creation to finished_at for XLSX import batches.",
    labelnames=["result"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
    registry=_registry,
)


def record_outbox_execution(
    *,
    stream: str,
    event_type: str,
    result: str,
    start_ts: datetime | None,
    end_ts: datetime | None,
) -> None:
    """result is success | failed | dead_letter."""
    OUTBOX_EXECUTIONS.labels(stream=stream, event_type=event_type, result=result).inc()
    if (
        result == "success"
        and start_ts is not None
        and end_ts is not None
        and end_ts >= start_ts
    ):
        seconds = (end_ts - start_ts).total_seconds()
        OUTBOX_PUBLISH_TO_PROCESSED.labels(
            stream=stream, event_type=event_type
        ).observe(seconds)


def record_import_batch_finished(
    *,
    result: str,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> None:
    """result: failed | completed | completed_with_errors"""
    IMPORT_BATCHES_COMPLETED.labels(result=result).inc()
    if started_at is not None and finished_at is not None and finished_at >= started_at:
        IMPORT_BATCH_DURATION.labels(result=result).observe(
            (finished_at - started_at).total_seconds()
        )


class _OrmMetricsCollector:
    """Yields GaugeMetricFamily from Django ORM on each scrape."""

    def collect(self):
        from django.db.models import Count, F, Min, Sum
        from django.utils import timezone

        from apps.integrations.hidrive.auth import get_hidrive_refresh_metrics
        from apps.intake.models import IntakeOutboxEvent, IntakeOutboxStatus
        from apps.outbox.models import OutboxEvent, OutboxStatus
        from apps.reception.models import PatientImportBatch

        now = timezone.now()

        # --- Medical outbox events (Gauge snapshot) ---
        g_outbox = GaugeMetricFamily(
            "cogitomedica_outbox_events_total",
            "Total number of medical outbox events by type and status.",
            labels=["event_type", "status"],
        )
        rows = list(
            OutboxEvent.objects.values("event_type", "status").annotate(
                count=Count("id")
            )
        )
        if rows:
            for row in rows:
                g_outbox.add_metric(
                    [row["event_type"], row["status"]], float(row["count"])
                )
        else:
            g_outbox.add_metric(["none", "none"], 0.0)
        yield g_outbox

        g_age = GaugeMetricFamily(
            "cogitomedica_outbox_pending_age_seconds",
            "Age in seconds of the oldest pending/failed medical outbox event.",
            labels=["event_type"],
        )
        oldest = (
            OutboxEvent.objects.filter(
                status__in=[OutboxStatus.PENDING, OutboxStatus.FAILED]
            )
            .values("event_type")
            .annotate(oldest_created=Min("created_at"))
        )
        oldest_list = list(oldest)
        if oldest_list:
            for row in oldest_list:
                age = (now - row["oldest_created"]).total_seconds()
                g_age.add_metric([row["event_type"]], max(0.0, age))
        else:
            g_age.add_metric(["none"], 0.0)
        yield g_age

        g_dur_sum = GaugeMetricFamily(
            "cogitomedica_outbox_processing_duration_seconds_sum",
            "Total processing duration in seconds (medical; publish to processed).",
            labels=["event_type"],
        )
        g_dur_cnt = GaugeMetricFamily(
            "cogitomedica_outbox_processing_duration_seconds_count",
            "Count for medical outbox processing duration.",
            labels=["event_type"],
        )
        durations = (
            OutboxEvent.objects.filter(
                status=OutboxStatus.PROCESSED,
                processed_at__isnull=False,
                medical_document_version__published_at__isnull=False,
            )
            .values("event_type")
            .annotate(
                total_time=Sum(
                    F("processed_at") - F("medical_document_version__published_at")
                ),
                count=Count("id"),
            )
        )
        dur_list = list(durations)
        if dur_list:
            for row in dur_list:
                val_sum = (
                    row["total_time"].total_seconds() if row["total_time"] else 0.0
                )
                val_count = float(row["count"] or 0)
                g_dur_sum.add_metric([row["event_type"]], val_sum)
                g_dur_cnt.add_metric([row["event_type"]], val_count)
        else:
            for et in OUTBOX_EVENT_TYPES:
                g_dur_sum.add_metric([et], 0.0)
                g_dur_cnt.add_metric([et], 0.0)
        yield g_dur_sum
        yield g_dur_cnt

        # --- Intake outbox (Gauge snapshot) ---
        g_intake = GaugeMetricFamily(
            "cogitomedica_intake_outbox_events_total",
            "Total number of intake outbox events by type and status.",
            labels=["event_type", "status"],
        )
        irows = list(
            IntakeOutboxEvent.objects.values("event_type", "status").annotate(
                count=Count("id")
            )
        )
        if irows:
            for row in irows:
                g_intake.add_metric(
                    [row["event_type"], row["status"]], float(row["count"])
                )
        else:
            g_intake.add_metric(["none", "none"], 0.0)
        yield g_intake

        g_iage = GaugeMetricFamily(
            "cogitomedica_intake_outbox_pending_age_seconds",
            "Age in seconds of the oldest pending/failed intake outbox event.",
            labels=["event_type"],
        )
        ioldest = (
            IntakeOutboxEvent.objects.filter(
                status__in=[IntakeOutboxStatus.PENDING, IntakeOutboxStatus.FAILED]
            )
            .values("event_type")
            .annotate(oldest_created=Min("created_at"))
        )
        ioldest_list = list(ioldest)
        if ioldest_list:
            for row in ioldest_list:
                age = (now - row["oldest_created"]).total_seconds()
                g_iage.add_metric([row["event_type"]], max(0.0, age))
        else:
            g_iage.add_metric(["none"], 0.0)
        yield g_iage

        g_isum = GaugeMetricFamily(
            "cogitomedica_intake_outbox_processing_duration_seconds_sum",
            "Total processing duration (intake; version created_at to processed_at).",
            labels=["event_type"],
        )
        g_icnt = GaugeMetricFamily(
            "cogitomedica_intake_outbox_processing_duration_seconds_count",
            "Count for intake outbox processing duration.",
            labels=["event_type"],
        )
        idurs = (
            IntakeOutboxEvent.objects.filter(
                status=IntakeOutboxStatus.PROCESSED,
                processed_at__isnull=False,
            )
            .values("event_type")
            .annotate(
                total_time=Sum(
                    F("processed_at") - F("intake_document_version__created_at")
                ),
                count=Count("id"),
            )
        )
        idur_list = list(idurs)
        if idur_list:
            for row in idur_list:
                val_sum = (
                    row["total_time"].total_seconds() if row["total_time"] else 0.0
                )
                val_count = float(row["count"] or 0)
                g_isum.add_metric([row["event_type"]], val_sum)
                g_icnt.add_metric([row["event_type"]], val_count)
        else:
            for et in INTAKE_OUTBOX_EVENT_TYPES:
                g_isum.add_metric([et], 0.0)
                g_icnt.add_metric([et], 0.0)
        yield g_isum
        yield g_icnt

        # --- Import batches / rows ---
        g_batches = GaugeMetricFamily(
            "cogitomedica_import_batches_total",
            "Total number of import batches by status.",
            labels=["status"],
        )
        batch_counts = list(
            PatientImportBatch.objects.values("status").annotate(count=Count("id"))
        )
        if batch_counts:
            for row in batch_counts:
                g_batches.add_metric([row["status"]], float(row["count"]))
        else:
            g_batches.add_metric(["none"], 0.0)
        yield g_batches

        g_rows = GaugeMetricFamily(
            "cogitomedica_import_rows_total",
            "Total number of imported rows (inserted vs error).",
            labels=["status"],
        )
        row_stats = PatientImportBatch.objects.aggregate(
            total_inserted=Sum("inserted_rows"), total_error=Sum("error_rows")
        )
        g_rows.add_metric(["inserted"], float(row_stats["total_inserted"] or 0))
        g_rows.add_metric(["error"], float(row_stats["total_error"] or 0))
        yield g_rows

        g_hid = GaugeMetricFamily(
            "cogitomedica_hidrive_token_refresh_total",
            "HiDrive token refresh attempts by outcome.",
            labels=["outcome"],
        )
        refresh_stats = get_hidrive_refresh_metrics()
        g_hid.add_metric(["attempt"], float(refresh_stats.get("attempt", 0.0)))
        g_hid.add_metric(["error"], float(refresh_stats.get("error", 0.0)))
        yield g_hid

        # --- Active doctors / patients (usage; no PHI in labels) ---
        yield from _collect_active_usage_gauges(now)


def _collect_active_usage_gauges(now):
    """Snapshot gauges for Grafana usage panels (doctors working, portal patients)."""
    from datetime import timedelta

    from apps.medical.constants import DOCUMENT_LOCK_TIMEOUT_HOURS
    from apps.medical.models import MedicalDocument
    from apps.operations.models import AuditEvent
    from apps.users.models import ROLE_GROUP_NAME_MAP, StaffUser

    doctor_group = ROLE_GROUP_NAME_MAP["DOCTOR"]

    g_active = GaugeMetricFamily(
        "cogitomedica_active_users",
        "Distinct active users in a time window (no PHI). "
        "channel=doctor: Doctor-group staff with last_login or AuditEvent as actor; "
        "channel=patient_portal: patients with successful portal activity audits.",
        labels=["channel", "window"],
    )

    for window_label, minutes in ACTIVE_USER_WINDOWS_MINUTES:
        since = now - timedelta(minutes=minutes)

        doctor_ids = set(
            StaffUser.objects.filter(
                groups__name=doctor_group,
                is_active=True,
                last_login__gte=since,
            ).values_list("id", flat=True)
        )
        doctor_ids.update(
            AuditEvent.objects.filter(
                event_time__gte=since,
                actor_user_id__isnull=False,
                actor_user__is_active=True,
                actor_user__groups__name=doctor_group,
            )
            .values_list("actor_user_id", flat=True)
            .distinct()
        )
        g_active.add_metric(["doctor", window_label], float(len(doctor_ids)))

        patient_count = (
            AuditEvent.objects.filter(
                event_time__gte=since,
                patient_id__isnull=False,
                event_type__in=PATIENT_PORTAL_ACTIVITY_EVENT_TYPES,
            )
            .values("patient_id")
            .distinct()
            .count()
        )
        g_active.add_metric(["patient_portal", window_label], float(patient_count))

    yield g_active

    lock_since = now - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS)
    editing = (
        MedicalDocument.objects.filter(
            locked_by_user_id__isnull=False,
            locked_at__isnull=False,
            locked_at__gte=lock_since,
            locked_by_user__is_active=True,
            locked_by_user__groups__name=doctor_group,
        )
        .values("locked_by_user_id")
        .distinct()
        .count()
    )
    g_editing = GaugeMetricFamily(
        "cogitomedica_doctors_editing",
        "Distinct Doctor-group staff currently holding a medical document lock "
        f"(locked_at within {DOCUMENT_LOCK_TIMEOUT_HOURS}h).",
        labels=[],
    )
    g_editing.add_metric([], float(editing))
    yield g_editing


def _ensure_components_registered() -> None:
    global _components_registered
    with _lock:
        if _components_registered:
            return
        _registry.register(_OrmMetricsCollector())
        _components_registered = True


def build_metrics_payload() -> bytes:
    """Full Prometheus exposition including ORM Gauges and runtime Counters/Histograms."""
    _ensure_components_registered()
    return generate_latest(_registry)
