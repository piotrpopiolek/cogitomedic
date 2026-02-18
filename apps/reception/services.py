from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.exceptions import DomainError, StateTransitionError
from apps.operations.services import create_audit_event
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientContactHistory,
    PatientFormSession,
    QueueEntry,
    QueueEntryStatus,
    QueueShift,
    QueueSource,
    QueueStatus,
    TabletDevice,
)


class InvalidLocaleError(DomainError):
    """Raised when locale for tablet session is unsupported."""


@dataclass(frozen=True)
class IssuedSessionToken:
    """Return payload for newly issued plain token + session metadata."""

    token_plain: str
    session_id: uuid.UUID
    expires_at: timezone.datetime


@dataclass(frozen=True)
class MergedPatientsResult:
    merged: bool
    source_patient_id: uuid.UUID
    target_patient_id: uuid.UUID
    moved_queue_entries: int
    moved_intake_forms: int
    moved_medical_documents: int
    identity_alert_closed: bool


def _is_supported_locale(locale: str) -> bool:
    normalized = locale.strip().lower()
    return normalized in {"de", "de-de", "en", "en-gb", "en-us"}


def _build_patient_identity_alert_window() -> tuple[timezone.datetime, timezone.datetime]:
    created_at = timezone.now()
    resolution_due_at = created_at + timedelta(hours=24)
    return created_at, resolution_due_at


@transaction.atomic
def create_or_update_patient_manual(
    *,
    first_name: str,
    last_name: str,
    date_of_birth: timezone.datetime.date,
    phone: str,
    email: str,
    created_or_updated_by_user_id: uuid.UUID,
    doctolib_patient_id: str | None = None,
    patient_id: uuid.UUID | None = None,
) -> Patient:
    """
    Create/update patient in manual flow with temporary identity alert handling.

    When `doctolib_patient_id` is missing, alert timestamps are set to satisfy the
    temporary-identity contract from the domain model and DB constraints.
    """

    # The actor id is part of the service signature for audit extension in next steps.
    _ = created_or_updated_by_user_id

    patient = Patient.objects.select_for_update().filter(id=patient_id).first() if patient_id else Patient()
    patient.first_name = first_name
    patient.last_name = last_name
    patient.date_of_birth = date_of_birth
    patient.phone = phone
    patient.email = email
    patient.doctolib_patient_id = doctolib_patient_id or None

    if not patient.doctolib_patient_id:
        if not patient.identity_alert_created_at or not patient.identity_resolution_due_at:
            (
                patient.identity_alert_created_at,
                patient.identity_resolution_due_at,
            ) = _build_patient_identity_alert_window()
    else:
        patient.identity_alert_created_at = None
        patient.identity_resolution_due_at = None

    patient.save()
    return patient


@transaction.atomic
def create_daily_queue(
    *,
    queue_date: timezone.datetime.date,
    clinic_site_id: uuid.UUID,
    consulting_room_id: uuid.UUID,
    shift_code: str,
    created_by_user_id: uuid.UUID,
    source: str = QueueSource.MANUAL,
) -> DailyQueue:
    """Create a daily queue for date/site/room/shift. Raises StateTransitionError if slot exists."""
    ClinicSite.objects.get(id=clinic_site_id)
    room = ConsultingRoom.objects.get(id=consulting_room_id)
    if str(room.clinic_site_id) != str(clinic_site_id):
        raise DomainError("Consulting room does not belong to the given clinic site.")
    if shift_code not in [c[0] for c in QueueShift.choices]:
        raise DomainError(f"Invalid shift_code: {shift_code}.")
    if source not in [c[0] for c in QueueSource.choices]:
        raise DomainError(f"Invalid source: {source}.")
    if DailyQueue.objects.filter(
        queue_date=queue_date,
        clinic_site_id=clinic_site_id,
        consulting_room_id=consulting_room_id,
        shift_code=shift_code,
    ).exists():
        raise StateTransitionError("Duplicate queue for this date/site/room/shift.")
    return DailyQueue.objects.create(
        queue_date=queue_date,
        clinic_site_id=clinic_site_id,
        consulting_room_id=consulting_room_id,
        shift_code=shift_code,
        source=source,
        status=QueueStatus.OPEN,
        created_by_user_id=created_by_user_id,
    )


@transaction.atomic
def update_daily_queue_status(
    daily_queue_id: uuid.UUID,
    *,
    status: str,
) -> DailyQueue:
    """Update queue status (OPEN/CLOSED)."""
    if status not in [c[0] for c in QueueStatus.choices]:
        raise DomainError(f"Invalid status: {status}.")
    queue = DailyQueue.objects.select_for_update().get(id=daily_queue_id)
    queue.status = status
    queue.save(update_fields=["status", "updated_at"])
    return queue


@transaction.atomic
def update_queue_entry(
    queue_entry_id: uuid.UUID,
    *,
    entry_status: str | None = None,
    notes: str | None = None,
) -> QueueEntry:
    """Update queue entry status and/or notes. DELETE semantic = set CANCELLED."""
    if entry_status is not None and entry_status not in [c[0] for c in QueueEntryStatus.choices]:
        raise DomainError(f"Invalid entry_status: {entry_status}.")
    entry = QueueEntry.objects.select_for_update().get(id=queue_entry_id)
    update_fields: list[str] = ["updated_at"]
    if entry_status is not None:
        entry.entry_status = entry_status
        update_fields.append("entry_status")
    if notes is not None:
        entry.notes = notes
        update_fields.append("notes")
    entry.save(update_fields=update_fields)
    return entry


@transaction.atomic
def merge_temporary_patient_into_confirmed(
    *,
    source_patient_id: uuid.UUID,
    target_patient_id: uuid.UUID,
    source_action: str,
    reason: str | None,
    actor_user_id: uuid.UUID | None = None,
) -> MergedPatientsResult:
    """Merge source temporary patient into target confirmed patient."""
    if source_patient_id == target_patient_id:
        raise StateTransitionError("Source and target patients must differ.")
    if source_action not in {"ARCHIVE", "KEEP_ACTIVE"}:
        raise DomainError("INVALID_SOURCE_ACTION")

    source = Patient.objects.select_for_update().get(id=source_patient_id)
    target = Patient.objects.select_for_update().get(id=target_patient_id)

    if source.identity_status != "TEMPORARY":
        raise DomainError("SOURCE_NOT_TEMPORARY")
    if target.identity_status != "CONFIRMED":
        raise DomainError("TARGET_NOT_CONFIRMED")

    queue_entries_qs = QueueEntry.objects.select_for_update().filter(patient_id=source_patient_id)
    queue_entry_ids = list(queue_entries_qs.values_list("id", flat=True))
    moved_queue_entries = len(queue_entry_ids)

    # Lazy imports avoid coupling at import time between app modules.
    from apps.intake.models import PatientIntakeForm
    from apps.medical.models import MedicalDocument

    moved_intake_forms = PatientIntakeForm.objects.filter(queue_entry_id__in=queue_entry_ids).count()
    moved_medical_documents = MedicalDocument.objects.filter(queue_entry_id__in=queue_entry_ids).count()

    now = timezone.now()
    if moved_queue_entries:
        queue_entries_qs.update(patient_id=target_patient_id, updated_at=now)

    PatientContactHistory.objects.filter(patient_id=source_patient_id).update(patient_id=target_patient_id)

    identity_alert_closed = False
    if source_action == "ARCHIVE":
        source.is_active = False
        source.identity_resolution_due_at = now
        source.save(update_fields=["is_active", "identity_resolution_due_at", "updated_at"])
        identity_alert_closed = True

    create_audit_event(
        event_type="PATIENT_MERGED",
        actor_user_id=actor_user_id,
        patient_id=target.id,
        metadata={
            "source_patient_id": str(source.id),
            "target_patient_id": str(target.id),
            "source_action": source_action,
            "reason": reason,
            "moved_entities": {
                "queue_entries": moved_queue_entries,
                "intake_forms": moved_intake_forms,
                "medical_documents": moved_medical_documents,
            },
            "identity_alert_closed": identity_alert_closed,
        },
    )

    return MergedPatientsResult(
        merged=True,
        source_patient_id=source.id,
        target_patient_id=target.id,
        moved_queue_entries=moved_queue_entries,
        moved_intake_forms=moved_intake_forms,
        moved_medical_documents=moved_medical_documents,
        identity_alert_closed=identity_alert_closed,
    )


@transaction.atomic
def create_queue_entry(
    *,
    daily_queue_id: uuid.UUID,
    patient_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    appointment_time: timezone.datetime | None = None,
    visit_external_id: str | None = None,
    notes: str | None = None,
) -> QueueEntry:
    """Create queue entry and auto-assign next position for the queue."""
    daily_queue = DailyQueue.objects.select_for_update().get(id=daily_queue_id)
    if daily_queue.status != QueueStatus.OPEN:
        raise StateTransitionError("Cannot add patient to closed queue.")

    next_position = (
        QueueEntry.objects.select_for_update()
        .filter(daily_queue_id=daily_queue_id)
        .aggregate(max_position=Max("position_no"))
        .get("max_position")
        or 0
    ) + 1

    return QueueEntry.objects.create(
        daily_queue_id=daily_queue_id,
        patient_id=patient_id,
        created_by_user_id=created_by_user_id,
        position_no=next_position,
        appointment_time=appointment_time,
        visit_external_id=visit_external_id,
        notes=notes,
    )


@transaction.atomic
def issue_tablet_session_token_latest_wins(
    *,
    queue_entry_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    form_locale: str = "de-DE",
    expires_in_minutes: int = 20,
    tablet_device_id: uuid.UUID | None = None,
) -> IssuedSessionToken:
    """
    Issue a fresh tablet token in latest-wins mode.

    Previous sessions stay in history; `queue_entry.active_session_id` is switched
    atomically to the newly created session.
    """
    if expires_in_minutes <= 0:
        raise DomainError("expires_in_minutes must be positive.")
    if not _is_supported_locale(form_locale):
        raise InvalidLocaleError(f"Unsupported locale '{form_locale}'.")

    queue_entry = QueueEntry.objects.select_for_update().get(id=queue_entry_id)

    token_plain = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token_plain.encode("utf-8")).hexdigest()

    tablet_device: TabletDevice | None = None
    if tablet_device_id:
        tablet_device = TabletDevice.objects.get(id=tablet_device_id, is_active=True)

    session = PatientFormSession.objects.create(
        queue_entry=queue_entry,
        tablet_device=tablet_device,
        token_hash=token_hash,
        form_locale=form_locale,
        expires_at=timezone.now() + timedelta(minutes=expires_in_minutes),
        created_by_user_id=created_by_user_id,
    )

    queue_entry.active_session = session
    queue_entry.save(update_fields=["active_session", "updated_at"])

    return IssuedSessionToken(
        token_plain=token_plain,
        session_id=session.id,
        expires_at=session.expires_at,
    )
