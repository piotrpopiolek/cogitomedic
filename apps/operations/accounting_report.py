"""Weekly accounting report (Befund first publications)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from apps.medical.models import (
    DocVersionStatus,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
)
from apps.users.display import staff_user_display_name

if TYPE_CHECKING:
    from apps.reception.models import Patient

ACCOUNTING_PAYMENT_COLUMNS_ENABLED = False

ACCOUNTING_REPORT_EXPORT_HEADER_SPECS: tuple[tuple[str, str], ...] = (
    ("administration.accounting_col_nr", "Nr"),
    ("administration.accounting_col_first_name", "Vorname"),
    ("administration.accounting_col_last_name", "Nachname"),
    ("administration.accounting_col_street", "Straße"),
    ("administration.accounting_col_postal_city", "PLZ/Ort"),
    ("administration.accounting_col_email", "Email"),
    ("administration.accounting_col_befund_doctor", "Befund-Arzt"),
    ("administration.accounting_col_exam_date", "Untersuchungsdatum"),
)

# Backward-compatible alias for tests and default export headers (DE canonical).
ACCOUNTING_REPORT_HEADERS_DE = tuple(
    default for _, default in ACCOUNTING_REPORT_EXPORT_HEADER_SPECS
)


def accounting_report_export_headers_default() -> tuple[str, ...]:
    return ACCOUNTING_REPORT_HEADERS_DE


def resolve_accounting_report_export_headers(request) -> tuple[str, ...]:
    from apps.core.translation_service import get_admin_translation

    return tuple(
        get_admin_translation(request, key, default)
        for key, default in ACCOUNTING_REPORT_EXPORT_HEADER_SPECS
    )


def resolve_accounting_report_export_sheet_title(request) -> str:
    from apps.core.translation_service import get_admin_translation

    return get_admin_translation(
        request,
        "administration.accounting_export_sheet_title",
        "Patientendaten",
    )


@dataclass(frozen=True)
class AccountingReportRow:
    row_no: int
    first_name: str
    last_name: str
    street: str
    postal_city: str
    email: str
    doctor_name: str
    exam_date: str
    medical_document_id: UUID
    doctor_user_id: UUID | None


@dataclass(frozen=True)
class DoctorPublicationCount:
    doctor_user_id: UUID | None
    doctor_name: str
    count: int


@dataclass(frozen=True)
class AccountingReportResult:
    rows: list[AccountingReportRow]
    doctor_counts: list[DoctorPublicationCount]
    date_from: date
    date_to: date


def _local_tz() -> ZoneInfo:
    return ZoneInfo(settings.TIME_ZONE)


def default_report_week_range(*, today: date | None = None) -> tuple[date, date]:
    """Current calendar week Monday–Sunday in ``settings.TIME_ZONE``."""
    if today is None:
        today = timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def parse_report_date(value: str | None) -> date | None:
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def resolve_report_date_range(
    *,
    date_from_raw: str | None,
    date_to_raw: str | None,
) -> tuple[date, date]:
    default_from, default_to = default_report_week_range()
    date_from = parse_report_date(date_from_raw) or default_from
    date_to = parse_report_date(date_to_raw) or default_to
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def published_at_range_utc(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Inclusive local dates → ``[start, end)`` in UTC for ``published_at``."""
    tz = _local_tz()
    start_local = datetime.combine(date_from, time.min, tzinfo=tz)
    end_local = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def format_patient_street(patient: Patient | None) -> str:
    if patient is None:
        return ""
    return (patient.street or "").strip()


def format_patient_postal_city(patient: Patient | None) -> str:
    """German-style locality: ``PLZ Ort`` (postal code + city)."""
    if patient is None:
        return ""
    postal = (patient.postal_code or "").strip()
    city = (patient.city or "").strip()
    if postal and city:
        return f"{postal} {city}"
    return postal or city


def format_patient_address(patient: Patient | None) -> str:
    """Legacy combined address (street + postal/city) for callers that need one line."""
    parts: list[str] = []
    for value in (
        format_patient_street(patient),
        format_patient_postal_city(patient),
    ):
        if value:
            parts.append(value)
    return ", ".join(parts)


def format_doctor_name(user) -> str:
    if user is None:
        return ""
    return (staff_user_display_name(user) or "").strip()


def format_exam_date_display(queue_date: date | None) -> str:
    if queue_date is None:
        return ""
    return queue_date.strftime("%d.%m.%Y")


def accounting_report_versions_qs(
    *,
    date_from: date,
    date_to: date,
    scoped_clinic_site_ids: list[UUID] | None = None,
) -> QuerySet[MedicalDocumentVersion]:
    start_utc, end_utc = published_at_range_utc(date_from, date_to)
    qs = (
        MedicalDocumentVersion.objects.filter(
            version_status=DocVersionStatus.PUBLISHED,
            version_no=1,
            published_at__gte=start_utc,
            published_at__lt=end_utc,
            revoked_at__isnull=True,
        )
        .exclude(
            medical_document__source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD,
        )
        .select_related(
            "published_by_user",
            "medical_document__queue_entry__patient",
            "medical_document__queue_entry__daily_queue",
        )
        .order_by("published_at", "id")
    )
    if scoped_clinic_site_ids is not None:
        qs = qs.filter(
            medical_document__queue_entry__daily_queue__clinic_site_id__in=scoped_clinic_site_ids
        )
    return qs


def _row_from_version(
    version: MedicalDocumentVersion, *, row_no: int
) -> AccountingReportRow:
    queue_entry = version.medical_document.queue_entry
    patient = queue_entry.patient
    daily_queue = queue_entry.daily_queue
    doctor = version.published_by_user
    return AccountingReportRow(
        row_no=row_no,
        first_name=(patient.first_name or "").strip(),
        last_name=(patient.last_name or "").strip(),
        street=format_patient_street(patient),
        postal_city=format_patient_postal_city(patient),
        email=(patient.email or "").strip(),
        doctor_name=format_doctor_name(doctor),
        exam_date=format_exam_date_display(
            daily_queue.queue_date if daily_queue else None
        ),
        medical_document_id=version.medical_document_id,
        doctor_user_id=doctor.id if doctor else None,
    )


def doctor_publication_counts(
    rows: list[AccountingReportRow],
) -> list[DoctorPublicationCount]:
    totals: dict[UUID | None, DoctorPublicationCount] = {}
    for row in rows:
        key = row.doctor_user_id
        if key in totals:
            existing = totals[key]
            totals[key] = DoctorPublicationCount(
                doctor_user_id=existing.doctor_user_id,
                doctor_name=existing.doctor_name,
                count=existing.count + 1,
            )
        else:
            totals[key] = DoctorPublicationCount(
                doctor_user_id=key,
                doctor_name=row.doctor_name,
                count=1,
            )
    return sorted(totals.values(), key=lambda item: (-item.count, item.doctor_name))


def build_accounting_report(
    *,
    date_from: date,
    date_to: date,
    scoped_clinic_site_ids: list[UUID] | None = None,
) -> AccountingReportResult:
    versions = list(
        accounting_report_versions_qs(
            date_from=date_from,
            date_to=date_to,
            scoped_clinic_site_ids=scoped_clinic_site_ids,
        )
    )
    rows = [
        _row_from_version(version, row_no=index)
        for index, version in enumerate(versions, start=1)
    ]
    return AccountingReportResult(
        rows=rows,
        doctor_counts=doctor_publication_counts(rows),
        date_from=date_from,
        date_to=date_to,
    )
