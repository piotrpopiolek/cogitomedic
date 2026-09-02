"""Resolve duplicate active QueueEntry rows before unique (daily_queue, patient, process_type).

Used by reception.0045. After that migration has run on a database, do not change
KEEP/CANCEL semantics here — they will not re-apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence
from uuid import UUID

from django.db.models import Count
from django.utils import timezone

_STATUS_RANK = {
    "DOCTOR_IN_PROGRESS": 5,
    "PATIENT_COMPLETED": 4,
    "PAPER_INTAKE_COMPLETED": 3,
    "IN_PROGRESS": 2,
    "WAITING": 1,
}

_CLINICAL_STATUSES = frozenset(
    {
        "PATIENT_COMPLETED",
        "PAPER_INTAKE_COMPLETED",
        "DOCTOR_IN_PROGRESS",
    }
)
_SUBMITTED_INTAKE = frozenset({"SUBMITTED", "REOPENED"})


class AmbiguousQueueDuplicates(Exception):
    """More than one row in a group has clinical work; refuse to auto-cancel."""

    def __init__(self, keepers: Sequence[QueueDuplicateCandidate]) -> None:
        ids = ", ".join(str(row.id) for row in keepers)
        super().__init__(
            "Ambiguous duplicate queue entries (more than one has intake, "
            f"paper completion, or a medical document). Resolve by hand: {ids}"
        )
        self.keepers = list(keepers)


@dataclass(frozen=True)
class QueueDuplicateCandidate:
    id: UUID
    entry_status: str
    created_at: datetime
    has_submitted_or_reopened_intake: bool
    has_intake_form: bool
    has_paper_authorization: bool
    has_medical_document: bool
    has_form_session: bool

    @property
    def is_clinical_keep(self) -> bool:
        if self.has_submitted_or_reopened_intake or self.has_medical_document:
            return True
        return self.entry_status in _CLINICAL_STATUSES

    @property
    def is_in_progress_keep(self) -> bool:
        if self.entry_status == "IN_PROGRESS":
            return True
        return (
            self.has_paper_authorization
            or self.has_intake_form
            or self.has_form_session
        )

    @property
    def status_rank(self) -> int:
        return _STATUS_RANK.get(self.entry_status, 0)


def pick_keep_candidate(
    rows: Sequence[QueueDuplicateCandidate],
) -> QueueDuplicateCandidate:
    """Choose the single row to keep; extras become CANCELLED.

    Clinical work (submitted intake, completed/paper/doctor status, document)
    always wins over empty WAITING. Two clinical rows → AmbiguousQueueDuplicates.
    """
    if not rows:
        raise ValueError("pick_keep_candidate requires at least one row")
    clinical = [row for row in rows if row.is_clinical_keep]
    if len(clinical) > 1:
        raise AmbiguousQueueDuplicates(clinical)
    if len(clinical) == 1:
        return clinical[0]
    in_progress = [row for row in rows if row.is_in_progress_keep]
    if len(in_progress) == 1:
        return in_progress[0]
    pool = in_progress or list(rows)
    return sorted(
        pool, key=lambda row: (-row.status_rank, row.created_at, str(row.id))
    )[0]


def cancel_extra_queue_entries(
    *,
    QueueEntry: Any,
    PatientIntakeForm: Any,
    PaperIntakeAuthorization: Any,
    MedicalDocument: Any,
    PatientFormSession: Any,
    db_alias: str,
) -> int:
    """Cancel extras in duplicate groups. Returns how many rows were cancelled."""
    now = timezone.now()
    groups = (
        QueueEntry.objects.using(db_alias)
        .exclude(entry_status="CANCELLED")
        .values("daily_queue_id", "patient_id", "process_type")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    to_cancel: list = []
    paper_revoke_ids: list[UUID] = []
    for group in groups:
        rows = list(
            QueueEntry.objects.using(db_alias)
            .select_for_update()
            .filter(
                daily_queue_id=group["daily_queue_id"],
                patient_id=group["patient_id"],
                process_type=group["process_type"],
            )
            .exclude(entry_status="CANCELLED")
        )
        if len(rows) < 2:
            continue
        candidates = _candidates_for_rows(
            rows,
            PatientIntakeForm=PatientIntakeForm,
            PaperIntakeAuthorization=PaperIntakeAuthorization,
            MedicalDocument=MedicalDocument,
            PatientFormSession=PatientFormSession,
            db_alias=db_alias,
        )
        keep_id = pick_keep_candidate(candidates).id
        for extra in rows:
            if extra.id == keep_id:
                continue
            extra.entry_status = "CANCELLED"
            extra.updated_at = now
            extra.doctor_list_sort_at = None
            to_cancel.append(extra)
            paper_revoke_ids.append(extra.id)
    if to_cancel:
        QueueEntry.objects.using(db_alias).bulk_update(
            to_cancel, ["entry_status", "updated_at", "doctor_list_sort_at"]
        )
    if paper_revoke_ids:
        PaperIntakeAuthorization.objects.using(db_alias).filter(
            queue_entry_id__in=paper_revoke_ids
        ).delete()
    return len(to_cancel)


def _candidates_for_rows(
    rows: Sequence[Any],
    *,
    PatientIntakeForm: Any,
    PaperIntakeAuthorization: Any,
    MedicalDocument: Any,
    PatientFormSession: Any,
    db_alias: str,
) -> list[QueueDuplicateCandidate]:
    entry_ids = [row.id for row in rows]
    forms = {
        form.queue_entry_id: form.form_status
        for form in PatientIntakeForm.objects.using(db_alias).filter(
            queue_entry_id__in=entry_ids
        )
    }
    paper_ids = set(
        PaperIntakeAuthorization.objects.using(db_alias)
        .filter(queue_entry_id__in=entry_ids)
        .values_list("queue_entry_id", flat=True)
    )
    doc_ids = set(
        MedicalDocument.objects.using(db_alias)
        .filter(queue_entry_id__in=entry_ids)
        .values_list("queue_entry_id", flat=True)
    )
    session_ids = set(
        PatientFormSession.objects.using(db_alias)
        .filter(queue_entry_id__in=entry_ids)
        .values_list("queue_entry_id", flat=True)
    )
    out: list[QueueDuplicateCandidate] = []
    for row in rows:
        status = forms.get(row.id)
        out.append(
            QueueDuplicateCandidate(
                id=row.id,
                entry_status=row.entry_status,
                created_at=row.created_at,
                has_submitted_or_reopened_intake=status in _SUBMITTED_INTAKE,
                has_intake_form=status is not None,
                has_paper_authorization=row.id in paper_ids,
                has_medical_document=row.id in doc_ids,
                has_form_session=row.id in session_ids,
            )
        )
    return out
