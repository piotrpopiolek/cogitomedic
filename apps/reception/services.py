from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.exceptions import DomainError, StateTransitionError
from apps.intake.models import PatientIntakeForm
from apps.medical.models import MedicalDocument
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
from apps.users.models import StaffUser


class InvalidLocaleError(DomainError):
    """Raised when locale for tablet session is unsupported."""


class InvalidSourceActionError(DomainError):
    """Raised when merge source action is unsupported."""


class SourceNotTemporaryError(DomainError):
    """Raised when merge source patient is not temporary."""


class TargetNotConfirmedError(DomainError):
    """Raised when merge target patient is not confirmed."""


@dataclass(frozen=True)
class IssuedSessionResult:
    """Return payload for newly created session (no token)."""

    session_id: uuid.UUID
    expires_at: timezone.datetime
    intake_form_id: uuid.UUID


@dataclass(frozen=True)
class MergedPatientsResult:
    merged: bool
    source_patient_id: uuid.UUID
    target_patient_id: uuid.UUID
    moved_queue_entries: int
    moved_intake_forms: int
    moved_medical_documents: int
    identity_alert_closed: bool


@transaction.atomic
def create_clinic_site(*, code: str, name: str, is_active: bool = True) -> ClinicSite:
    """Create a clinic site."""
    return ClinicSite.objects.create(code=code, name=name, is_active=is_active)


@transaction.atomic
def update_clinic_site(
    *,
    clinic_site_id: uuid.UUID,
    code: str | None = None,
    name: str | None = None,
    is_active: bool | None = None,
) -> ClinicSite:
    """Update mutable clinic site fields."""
    site = ClinicSite.objects.select_for_update().get(id=clinic_site_id)
    update_fields: list[str] = []
    if code is not None:
        site.code = code
        update_fields.append("code")
    if name is not None:
        site.name = name
        update_fields.append("name")
    if is_active is not None:
        site.is_active = is_active
        update_fields.append("is_active")
    if not update_fields:
        raise DomainError("Provide at least one field to update.")
    site.save(update_fields=update_fields)
    return site


@transaction.atomic
def deactivate_clinic_site(*, clinic_site_id: uuid.UUID) -> ClinicSite:
    """Soft-deactivate clinic site."""
    site = ClinicSite.objects.select_for_update().get(id=clinic_site_id)
    if site.is_active:
        site.is_active = False
        site.save(update_fields=["is_active"])
    return site


@transaction.atomic
def create_consulting_room(
    *,
    clinic_site_id: uuid.UUID,
    code: str,
    name: str,
    is_active: bool = True,
) -> ConsultingRoom:
    """Create consulting room for a clinic site."""
    ClinicSite.objects.get(id=clinic_site_id)
    return ConsultingRoom.objects.create(
        clinic_site_id=clinic_site_id,
        code=code,
        name=name,
        is_active=is_active,
    )


@transaction.atomic
def update_consulting_room(
    *,
    consulting_room_id: uuid.UUID,
    clinic_site_id: uuid.UUID | None = None,
    code: str | None = None,
    name: str | None = None,
    is_active: bool | None = None,
) -> ConsultingRoom:
    """Update mutable consulting room fields."""
    room = ConsultingRoom.objects.select_for_update().get(id=consulting_room_id)
    update_fields: list[str] = []
    if clinic_site_id is not None:
        ClinicSite.objects.get(id=clinic_site_id)
        room.clinic_site_id = clinic_site_id
        update_fields.append("clinic_site")
    if code is not None:
        room.code = code
        update_fields.append("code")
    if name is not None:
        room.name = name
        update_fields.append("name")
    if is_active is not None:
        room.is_active = is_active
        update_fields.append("is_active")
    if not update_fields:
        raise DomainError("Provide at least one field to update.")
    room.save(update_fields=update_fields)
    return room


@transaction.atomic
def deactivate_consulting_room(*, consulting_room_id: uuid.UUID) -> ConsultingRoom:
    """Soft-deactivate consulting room."""
    room = ConsultingRoom.objects.select_for_update().get(id=consulting_room_id)
    if room.is_active:
        room.is_active = False
        room.save(update_fields=["is_active"])
    return room


@transaction.atomic
def create_tablet_device(*, android_id: str, is_active: bool = True) -> TabletDevice:
    """Create a tablet device (identified by android_id only)."""
    return TabletDevice.objects.create(android_id=android_id, is_active=is_active)


def get_or_create_tablet_device_by_android_id(*, android_id: str) -> tuple[TabletDevice, bool]:
    """Get or create a tablet device by android_id (auto-registration). Returns (device, created)."""
    device, created = TabletDevice.objects.get_or_create(
        android_id=android_id,
        defaults={"is_active": True},
    )
    return device, created


@transaction.atomic
def update_tablet_device(
    *,
    tablet_device_id: uuid.UUID,
    android_id: str | None = None,
    is_active: bool | None = None,
) -> TabletDevice:
    """Update mutable tablet fields."""
    device = TabletDevice.objects.select_for_update().get(id=tablet_device_id)
    update_fields: list[str] = []
    if android_id is not None:
        device.android_id = android_id
        update_fields.append("android_id")
    if is_active is not None:
        device.is_active = is_active
        update_fields.append("is_active")
    if not update_fields:
        raise DomainError("Provide at least one field to update.")
    device.save(update_fields=update_fields)
    return device


@transaction.atomic
def deactivate_tablet_device(*, tablet_device_id: uuid.UUID) -> TabletDevice:
    """Soft-deactivate tablet device."""
    device = TabletDevice.objects.select_for_update().get(id=tablet_device_id)
    if device.is_active:
        device.is_active = False
        device.save(update_fields=["is_active"])
    return device


@transaction.atomic
def mark_tablet_heartbeat(*, tablet_device_id: uuid.UUID) -> TabletDevice:
    """Update tablet last_seen_at timestamp."""
    device = TabletDevice.objects.select_for_update().get(id=tablet_device_id)
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])
    return device


def _is_supported_locale(locale: str) -> bool:
    normalized = locale.strip().lower()
    return normalized in {"de", "de-de", "en", "en-gb", "en-us", "pl", "pl-pl"}


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
    assigned_doctor_id: uuid.UUID | None = None,
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
    if assigned_doctor_id is not None:
        StaffUser.objects.get(id=assigned_doctor_id)
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
        assigned_doctor_id=assigned_doctor_id,
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


def _not_provided():
    """Sentinel for PATCH: field was not in request body."""
    return object()


NOT_PROVIDED = _not_provided()


@transaction.atomic
def update_daily_queue(
    daily_queue_id: uuid.UUID,
    *,
    status: str | None = None,
    assigned_doctor_id: uuid.UUID | None = NOT_PROVIDED,
) -> DailyQueue:
    """Update queue status and/or assigned doctor. At least one must be provided."""
    if status is None and assigned_doctor_id is NOT_PROVIDED:
        raise DomainError("At least one of status or assigned_doctor_id must be provided.")
    if status is not None and status not in [c[0] for c in QueueStatus.choices]:
        raise DomainError(f"Invalid status: {status}.")
    if assigned_doctor_id is not NOT_PROVIDED and assigned_doctor_id is not None:
        StaffUser.objects.get(id=assigned_doctor_id)
    queue = DailyQueue.objects.select_for_update().get(id=daily_queue_id)
    update_fields = ["updated_at"]
    if status is not None:
        queue.status = status
        update_fields.append("status")
    if assigned_doctor_id is not NOT_PROVIDED:
        queue.assigned_doctor_id = assigned_doctor_id
        update_fields.append("assigned_doctor_id")
    queue.save(update_fields=update_fields)
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
        raise InvalidSourceActionError("INVALID_SOURCE_ACTION")

    source = Patient.objects.select_for_update().get(id=source_patient_id)
    target = Patient.objects.select_for_update().get(id=target_patient_id)

    if source.identity_status != "TEMPORARY":
        raise SourceNotTemporaryError("SOURCE_NOT_TEMPORARY")
    if target.identity_status != "CONFIRMED":
        raise TargetNotConfirmedError("TARGET_NOT_CONFIRMED")

    queue_entries_qs = QueueEntry.objects.select_for_update().filter(patient_id=source_patient_id)
    queue_entry_ids = list(queue_entries_qs.values_list("id", flat=True))
    moved_queue_entries = len(queue_entry_ids)

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
def issue_tablet_session_latest_wins(
    *,
    queue_entry_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    form_locale: str = "de-DE",
    expires_in_minutes: int = 120,
    tablet_device_id: uuid.UUID | None = None,
) -> IssuedSessionResult:
    """
    Create or update form session in latest-wins mode (no token).

    Previous sessions stay in history; `queue_entry.active_session_id` is switched
    atomically to the newly created session.
    """
    if expires_in_minutes <= 0:
        raise DomainError("expires_in_minutes must be positive.")
    if not _is_supported_locale(form_locale):
        raise InvalidLocaleError(f"Unsupported locale '{form_locale}'.")

    queue_entry = QueueEntry.objects.select_for_update().get(id=queue_entry_id)

    tablet_device: TabletDevice | None = None
    if tablet_device_id:
        tablet_device = TabletDevice.objects.get(id=tablet_device_id, is_active=True)

    session = PatientFormSession.objects.create(
        queue_entry=queue_entry,
        tablet_device=tablet_device,
        form_locale=form_locale,
        expires_at=timezone.now() + timedelta(minutes=expires_in_minutes),
        created_by_user_id=created_by_user_id,
    )

    queue_entry.active_session = session
    queue_entry.save(update_fields=["active_session", "updated_at"])

    intake_form, created = PatientIntakeForm.objects.get_or_create(
        queue_entry_id=queue_entry.id,
        defaults={"session": session},
    )
    if not created:
        intake_form.session = session
        intake_form.save(update_fields=["session", "updated_at"])

    return IssuedSessionResult(
        session_id=session.id,
        expires_at=session.expires_at,
        intake_form_id=intake_form.id,
    )
