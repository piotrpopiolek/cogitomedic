"""Reception dashboard — missing HiDrive laboratory PDF matches."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.core.api_utils import get_scoped_clinic_site_ids
from apps.integrations.hidrive.client import HiDriveTimeoutError
from apps.intake.models import IntakeStatus
from apps.medical.incoming_pdf_scan import (
    IncomingMatchStatus,
    hidrive_incoming_dir,
    list_incoming_lab_pdf_rows,
    evaluate_patient_incoming_match,
    suggest_incoming_pdf_filename,
)
from apps.medical.models import MedicalDocStatus, MedicalDocumentSourceType
from apps.reception.models import QueueEntry, QueueEntryStatus

logger = logging.getLogger(__name__)

HIDRIVE_RESULT_COHORT_DAYS = 14
MISSING_HIDRIVE_RESULTS_DISPLAY_LIMIT = 100


@dataclass(frozen=True)
class MissingHiDriveResultRow:
    patient_name: str
    queue_date: date
    entry_status: str
    match_status: IncomingMatchStatus
    suggested_filename: str
    hours_waiting: float
    queue_entry_id: UUID
    rejected_filenames: tuple[str, ...] = ()


@dataclass(frozen=True)
class MissingHiDriveResultsReport:
    rows: list[MissingHiDriveResultRow]
    hidrive_status: IncomingMatchStatus
    scanned_at: datetime
    incoming_path: str
    total_row_count: int


def query_hidrive_result_candidates(
    *,
    scoped_clinic_site_ids: list[UUID] | None,
    queue_date_from: date,
) -> list[QueueEntry]:
    qs = (
        QueueEntry.objects.select_related(
            "patient",
            "daily_queue",
            "medical_document",
            "intake_form",
        )
        .filter(
            entry_status__in=[
                QueueEntryStatus.PATIENT_COMPLETED,
                QueueEntryStatus.DOCTOR_IN_PROGRESS,
                QueueEntryStatus.PAPER_INTAKE_COMPLETED,
            ],
            daily_queue__queue_date__gte=queue_date_from,
        )
        .exclude(entry_status=QueueEntryStatus.CANCELLED)
        .filter(
            Q(intake_form__form_status=IntakeStatus.SUBMITTED)
            | Q(entry_status=QueueEntryStatus.PAPER_INTAKE_COMPLETED)
        )
        .filter(
            Q(medical_document__isnull=True)
            | Q(
                medical_document__status=MedicalDocStatus.DRAFT,
                medical_document__source_type__in=[
                    MedicalDocumentSourceType.DIGITAL_INTAKE,
                    MedicalDocumentSourceType.PAPER_INTAKE,
                ],
            )
        )
        .exclude(medical_document__status=MedicalDocStatus.PUBLISHED)
        .exclude(
            medical_document__source_type=MedicalDocumentSourceType.EXTERNAL_UPLOAD
        )
        .order_by("-daily_queue__queue_date", "position_no")
    )
    if scoped_clinic_site_ids is not None:
        qs = qs.filter(daily_queue__clinic_site_id__in=scoped_clinic_site_ids)
    return list(qs)


def _hours_waiting_since_queue_date(queue_date: date) -> float:
    start = timezone.make_aware(datetime.combine(queue_date, time.min))
    return max(0.0, (timezone.now() - start).total_seconds() / 3600.0)


def build_missing_hidrive_results_report(user) -> MissingHiDriveResultsReport:
    scanned_at = timezone.now()
    incoming_path = hidrive_incoming_dir()
    dashboard_timeout = float(getattr(settings, "HIDRIVE_DASHBOARD_TIMEOUT_SECONDS", 8))
    scoped_clinic_site_ids = get_scoped_clinic_site_ids(user)
    queue_date_from = timezone.localdate() - timedelta(days=HIDRIVE_RESULT_COHORT_DAYS)

    try:
        listing = list_incoming_lab_pdf_rows(
            hidrive_total_timeout_seconds=dashboard_timeout,
        )
    except HiDriveTimeoutError:
        logger.warning(
            "hidrive_dashboard_timeout path=%s timeout_seconds=%s",
            incoming_path,
            dashboard_timeout,
        )
        return MissingHiDriveResultsReport(
            rows=[],
            hidrive_status=IncomingMatchStatus.HIDRIVE_ERROR,
            scanned_at=scanned_at,
            incoming_path=incoming_path,
            total_row_count=0,
        )

    if not listing.hidrive_ok:
        return MissingHiDriveResultsReport(
            rows=[],
            hidrive_status=IncomingMatchStatus.HIDRIVE_ERROR,
            scanned_at=scanned_at,
            incoming_path=incoming_path,
            total_row_count=0,
        )

    hidrive_status = (
        IncomingMatchStatus.FOLDER_EMPTY
        if listing.folder_empty
        else IncomingMatchStatus.OK
    )

    candidates = query_hidrive_result_candidates(
        scoped_clinic_site_ids=scoped_clinic_site_ids,
        queue_date_from=queue_date_from,
    )

    rows: list[MissingHiDriveResultRow] = []
    for entry in candidates:
        match = evaluate_patient_incoming_match(
            entry.patient,
            listing.pdf_rows,
            incoming_dir=listing.incoming_path,
        )
        if match.status == IncomingMatchStatus.MATCHED:
            continue
        if match.status not in (
            IncomingMatchStatus.NO_FILE,
            IncomingMatchStatus.AMBIGUOUS,
            IncomingMatchStatus.REJECTED_ONLY,
        ):
            continue

        patient = entry.patient
        rows.append(
            MissingHiDriveResultRow(
                patient_name=f"{patient.first_name} {patient.last_name}".strip(),
                queue_date=entry.daily_queue.queue_date,
                entry_status=entry.entry_status,
                match_status=match.status,
                suggested_filename=suggest_incoming_pdf_filename(patient),
                hours_waiting=_hours_waiting_since_queue_date(
                    entry.daily_queue.queue_date
                ),
                queue_entry_id=entry.id,
                rejected_filenames=match.rejected_filenames,
            )
        )

    return MissingHiDriveResultsReport(
        rows=rows,
        hidrive_status=hidrive_status,
        scanned_at=scanned_at,
        incoming_path=incoming_path,
        total_row_count=len(rows),
    )
