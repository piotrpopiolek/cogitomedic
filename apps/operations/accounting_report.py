"""Weekly accounting report (publications, attended visits, Ausfallhonorar)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from django.db.models import Min, OuterRef, Prefetch, Q, QuerySet, Subquery
from django.utils import timezone

from apps.intake.models import IntakeStatus
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
)
from apps.reception.models import QueueEntry, QueueEntryStatus
from apps.users.display import staff_user_display_name

if TYPE_CHECKING:
    from apps.reception.models import Patient

ACCOUNTING_PAYMENT_COLUMNS_ENABLED = False

ReportMode = Literal["published", "attended", "ausfall"]

REPORT_MODE_PUBLISHED: ReportMode = "published"
REPORT_MODE_ATTENDED: ReportMode = "attended"
REPORT_MODE_AUSFALL: ReportMode = "ausfall"
ACCOUNTING_REPORT_MODES: frozenset[str] = frozenset(
    {REPORT_MODE_PUBLISHED, REPORT_MODE_ATTENDED, REPORT_MODE_AUSFALL}
)

_ATTENDED_INTAKE_STATUSES = (IntakeStatus.SUBMITTED, IntakeStatus.REOPENED)


def _accounting_attended_q() -> Q:
    """Digital intake submitted/reopened, or paper-intake path completed."""
    return Q(entry_status=QueueEntryStatus.PAPER_INTAKE_COMPLETED) | Q(
        intake_form__form_status__in=_ATTENDED_INTAKE_STATUSES
    )


AUSFALLHONORAR_YES_DEFAULT = "Ja"
AUSFALLHONORAR_YES_KEY = "administration.accounting_ausfallhonorar_yes"
# Backward-compatible alias (DE fallback for cell value).
AUSFALLHONORAR_LABEL = AUSFALLHONORAR_YES_DEFAULT

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

ACCOUNTING_REPORT_AUSFALL_HEADER_SPEC: tuple[str, str] = (
    "administration.accounting_col_ausfallhonorar",
    "Ausfallhonorar",
)

# Backward-compatible alias for tests and default export headers (DE canonical).
ACCOUNTING_REPORT_HEADERS_DE = tuple(
    default for _, default in ACCOUNTING_REPORT_EXPORT_HEADER_SPECS
)


def accounting_report_export_headers_default() -> tuple[str, ...]:
    return ACCOUNTING_REPORT_HEADERS_DE


def resolve_accounting_report_export_headers(
    request, *, report_mode: ReportMode | str | None = REPORT_MODE_PUBLISHED
) -> tuple[str, ...]:
    from apps.core.translation_service import get_admin_translation

    mode = parse_report_mode(report_mode)
    specs = list(ACCOUNTING_REPORT_EXPORT_HEADER_SPECS)
    if mode == REPORT_MODE_AUSFALL:
        specs.append(ACCOUNTING_REPORT_AUSFALL_HEADER_SPEC)
    return tuple(get_admin_translation(request, key, default) for key, default in specs)


def resolve_accounting_report_export_sheet_title(request) -> str:
    from apps.core.translation_service import get_admin_translation

    return get_admin_translation(
        request,
        "administration.accounting_export_sheet_title",
        "Patientendaten",
    )


def resolve_accounting_ausfallhonorar_yes(request) -> str:
    """Localized Yes/Ja/Tak for Ausfallhonorar column cells (UI + export)."""
    from apps.core.translation_service import get_admin_translation

    return get_admin_translation(
        request,
        AUSFALLHONORAR_YES_KEY,
        AUSFALLHONORAR_YES_DEFAULT,
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
    medical_document_id: UUID | None
    doctor_user_id: UUID | None
    ausfallhonorar: str = ""


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
    report_mode: ReportMode = REPORT_MODE_PUBLISHED


def parse_report_mode(value: str | None) -> ReportMode:
    """Return report mode; ``None``/blank → ``published``. Unknown values raise ``ValueError``."""
    raw = (value or "").strip().lower()
    if not raw:
        return REPORT_MODE_PUBLISHED
    if raw in ACCOUNTING_REPORT_MODES:
        return raw  # type: ignore[return-value]
    allowed = ", ".join(sorted(ACCOUNTING_REPORT_MODES))
    raise ValueError(f"Invalid report_mode. Allowed: {allowed}.")


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


def normalize_postal_code_display(code: str | None) -> str:
    """Strip Excel float artifact (``17498.0``) from stored postal codes."""
    text = (code or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def format_patient_street(patient: Patient | None) -> str:
    if patient is None:
        return ""
    return (patient.street or "").strip()


def format_patient_postal_city(patient: Patient | None) -> str:
    """German-style locality: ``PLZ Ort`` (postal code + city)."""
    if patient is None:
        return ""
    postal = normalize_postal_code_display(patient.postal_code)
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
    """
    One row per document: the earliest non-revoked ``PUBLISHED`` version
    (lowest ``version_no``) whose exam day (``DailyQueue.queue_date``) falls in
    ``[date_from, date_to]`` inclusive.

    Normal amend (v1 kept, v2 published) still bills on v1. After revoke of v1
    and republish as v2, v2 is used so the visit is not dropped from billing.
    Date range follows the visit day, not ``published_at``.
    """
    earliest_non_revoked_version_no = (
        MedicalDocumentVersion.objects.filter(
            medical_document_id=OuterRef("medical_document_id"),
            version_status=DocVersionStatus.PUBLISHED,
            revoked_at__isnull=True,
        )
        .order_by()
        .values("medical_document_id")
        .annotate(min_version_no=Min("version_no"))
        .values("min_version_no")[:1]
    )
    qs = (
        MedicalDocumentVersion.objects.filter(
            version_status=DocVersionStatus.PUBLISHED,
            revoked_at__isnull=True,
            version_no=Subquery(earliest_non_revoked_version_no),
            medical_document__queue_entry__daily_queue__queue_date__gte=date_from,
            medical_document__queue_entry__daily_queue__queue_date__lte=date_to,
        )
        .exclude(
            medical_document__source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD,
        )
        .select_related(
            "published_by_user",
            "medical_document__queue_entry__patient",
            "medical_document__queue_entry__daily_queue",
        )
        .order_by(
            "medical_document__queue_entry__daily_queue__queue_date",
            "published_at",
            "id",
        )
    )
    if scoped_clinic_site_ids is not None:
        qs = qs.filter(
            medical_document__queue_entry__daily_queue__clinic_site_id__in=scoped_clinic_site_ids
        )
    return qs


def accounting_report_attended_qs(
    *,
    date_from: date,
    date_to: date,
    scoped_clinic_site_ids: list[UUID] | None = None,
) -> QuerySet[QueueEntry]:
    """
    Queue entries for patients who completed the visit path in the date range.

    Includes digital intake ``SUBMITTED``/``REOPENED`` and paper path
    ``PAPER_INTAKE_COMPLETED``. Excludes cancelled entries and import no-shows.
    Does not require a published Befund.
    """
    first_pub = Prefetch(
        "medical_document__versions",
        queryset=MedicalDocumentVersion.objects.filter(
            version_status=DocVersionStatus.PUBLISHED,
            revoked_at__isnull=True,
        )
        .order_by("version_no", "published_at", "id")
        .select_related("published_by_user"),
        to_attr="_accounting_first_publications",
    )
    qs = (
        QueueEntry.objects.filter(
            daily_queue__queue_date__gte=date_from,
            daily_queue__queue_date__lte=date_to,
        )
        .filter(_accounting_attended_q())
        .exclude(entry_status=QueueEntryStatus.CANCELLED)
        .select_related(
            "patient",
            "daily_queue",
            "medical_document",
        )
        .prefetch_related(first_pub)
        .order_by("daily_queue__queue_date", "position_no", "id")
    )
    if scoped_clinic_site_ids is not None:
        qs = qs.filter(daily_queue__clinic_site_id__in=scoped_clinic_site_ids)
    return qs


def accounting_report_ausfall_qs(
    *,
    date_from: date,
    date_to: date,
    scoped_clinic_site_ids: list[UUID] | None = None,
) -> QuerySet[QueueEntry]:
    """
    Queue entries in range that did not complete the visit path.

    = entries on the day minus attended (digital SUBMITTED/REOPENED or
    PAPER_INTAKE_COMPLETED), excluding cancelled.
    One bucket for accounting: no-show, refused exam, incomplete consents/intake.
    """
    qs = (
        QueueEntry.objects.filter(
            daily_queue__queue_date__gte=date_from,
            daily_queue__queue_date__lte=date_to,
        )
        .exclude(entry_status=QueueEntryStatus.CANCELLED)
        .exclude(_accounting_attended_q())
        .select_related("patient", "daily_queue", "medical_document")
        .order_by("daily_queue__queue_date", "position_no", "id")
    )
    if scoped_clinic_site_ids is not None:
        qs = qs.filter(daily_queue__clinic_site_id__in=scoped_clinic_site_ids)
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


def _medical_document_for_entry(entry: QueueEntry) -> MedicalDocument | None:
    try:
        return entry.medical_document
    except MedicalDocument.DoesNotExist:
        return None


def _doctor_for_attended_entry(entry: QueueEntry):
    """Earliest non-revoked publication author — no assigned_doctor fallback."""
    medical_document = _medical_document_for_entry(entry)
    if medical_document is None:
        return None
    versions = getattr(medical_document, "_accounting_first_publications", None) or []
    if not versions:
        return None
    return versions[0].published_by_user


def _row_from_attended_entry(entry: QueueEntry, *, row_no: int) -> AccountingReportRow:
    patient = entry.patient
    daily_queue = entry.daily_queue
    doctor = _doctor_for_attended_entry(entry)
    medical_document = _medical_document_for_entry(entry)
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
        medical_document_id=medical_document.id if medical_document else None,
        doctor_user_id=doctor.id if doctor else None,
    )


def _row_from_ausfall_entry(
    entry: QueueEntry,
    *,
    row_no: int,
    ausfallhonorar_yes: str = AUSFALLHONORAR_YES_DEFAULT,
) -> AccountingReportRow:
    patient = entry.patient
    daily_queue = entry.daily_queue
    medical_document = _medical_document_for_entry(entry)
    return AccountingReportRow(
        row_no=row_no,
        first_name=(patient.first_name or "").strip(),
        last_name=(patient.last_name or "").strip(),
        street=format_patient_street(patient),
        postal_city=format_patient_postal_city(patient),
        email=(patient.email or "").strip(),
        doctor_name="",
        exam_date=format_exam_date_display(
            daily_queue.queue_date if daily_queue else None
        ),
        medical_document_id=medical_document.id if medical_document else None,
        doctor_user_id=None,
        ausfallhonorar=ausfallhonorar_yes,
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
    report_mode: ReportMode | str | None = REPORT_MODE_PUBLISHED,
    ausfallhonorar_yes: str | None = None,
) -> AccountingReportResult:
    mode = parse_report_mode(report_mode)
    yes_label = (
        ausfallhonorar_yes
        if ausfallhonorar_yes is not None
        else AUSFALLHONORAR_YES_DEFAULT
    )
    if mode == REPORT_MODE_ATTENDED:
        entries = list(
            accounting_report_attended_qs(
                date_from=date_from,
                date_to=date_to,
                scoped_clinic_site_ids=scoped_clinic_site_ids,
            )
        )
        rows = [
            _row_from_attended_entry(entry, row_no=index)
            for index, entry in enumerate(entries, start=1)
        ]
    elif mode == REPORT_MODE_AUSFALL:
        entries = list(
            accounting_report_ausfall_qs(
                date_from=date_from,
                date_to=date_to,
                scoped_clinic_site_ids=scoped_clinic_site_ids,
            )
        )
        rows = [
            _row_from_ausfall_entry(entry, row_no=index, ausfallhonorar_yes=yes_label)
            for index, entry in enumerate(entries, start=1)
        ]
    else:
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
        report_mode=mode,
    )
