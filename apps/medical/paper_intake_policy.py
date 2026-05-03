from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Mapping

from django.utils import timezone

from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.medical.models import MedicalDocument, PaperIntakeAuthorization
from apps.medical.constants import PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT
from apps.reception.models import QueueEntry, QueueEntryStatus


@dataclass(frozen=True)
class PaperIntakeAuthorizeBlock:
    """One user-visible blocker; use *message_key* with ``resolve_other_message``."""

    message_key: str
    default_message: str
    format_params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperIntakeAuthorizeEligibility:
    has_document: bool
    active_authorization: PaperIntakeAuthorization | None
    can_authorize: bool
    can_revoke: bool
    blocking_blocks: tuple[PaperIntakeAuthorizeBlock, ...]
    earliest_authorize_at: datetime | None


def paper_intake_authorize_eligibility(
    *, entry: QueueEntry
) -> PaperIntakeAuthorizeEligibility:
    """
    Compute whether paper intake may be authorized (read-only).

    Ordering and conditions follow ``authorize_paper_intake`` where applicable, plus
    early exits for existing document / active authorization used by the HTML template.
    """
    has_document = MedicalDocument.objects.filter(queue_entry_id=entry.id).exists()
    active_authorization = (
        PaperIntakeAuthorization.objects.filter(queue_entry_id=entry.id)
        .select_related("authorized_by")
        .first()
    )

    if has_document:
        return PaperIntakeAuthorizeEligibility(
            has_document=True,
            active_authorization=active_authorization,
            can_authorize=False,
            can_revoke=False,
            blocking_blocks=(
                PaperIntakeAuthorizeBlock(
                    message_key="administration.paper_intake_admin_has_document",
                    default_message=(
                        "A medical document already exists for this queue entry."
                    ),
                ),
            ),
            earliest_authorize_at=None,
        )

    if active_authorization is not None:
        return PaperIntakeAuthorizeEligibility(
            has_document=False,
            active_authorization=active_authorization,
            can_authorize=False,
            can_revoke=True,
            blocking_blocks=(),
            earliest_authorize_at=None,
        )

    blocks: list[PaperIntakeAuthorizeBlock] = []
    earliest_at: datetime | None = None

    if entry.entry_status != QueueEntryStatus.WAITING:
        blocks.append(
            PaperIntakeAuthorizeBlock(
                message_key="other.domain.paper_intake_authorization_invalid_status",
                default_message="Queue entry is not in WAITING status.",
            )
        )

    if entry.appointment_time is None:
        blocks.append(
            PaperIntakeAuthorizeBlock(
                message_key="other.domain.paper_intake_requires_appointment_time",
                default_message="appointment_time is required for paper intake.",
            )
        )
    else:
        earliest_at = entry.appointment_time + timedelta(
            hours=PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT
        )
        if timezone.now() < earliest_at:
            blocks.append(
                PaperIntakeAuthorizeBlock(
                    message_key="other.domain.paper_intake_authorization_too_early",
                    default_message=(
                        "Paper intake authorization is only allowed at least 3 hours "
                        "after appointment time."
                    ),
                )
            )

    intake_row = (
        PatientIntakeForm.objects.filter(queue_entry_id=entry.id)
        .only("form_status")
        .first()
    )
    if intake_row is not None and intake_row.form_status == IntakeStatus.SUBMITTED:
        blocks.append(
            PaperIntakeAuthorizeBlock(
                message_key=(
                    "other.domain.paper_intake_authorization_intake_form_submitted"
                ),
                default_message=(
                    "Cannot authorize: the patient has submitted the digital intake form."
                ),
            )
        )

    return PaperIntakeAuthorizeEligibility(
        has_document=False,
        active_authorization=None,
        can_authorize=len(blocks) == 0,
        can_revoke=False,
        blocking_blocks=tuple(blocks),
        earliest_authorize_at=earliest_at,
    )
