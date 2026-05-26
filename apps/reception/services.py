from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.domain_messages import domain_message
from apps.core.otel_spans import cogito_business_span
from apps.core.exceptions import DomainError, StateTransitionError
from apps.intake.models import PatientIntakeForm
from apps.reception.models import (
    ClinicSite,
    ConsultingRoom,
    DailyQueue,
    Patient,
    PatientFormSession,
    QueueEntry,
    QueueEntryStatus,
    QueueShift,
    QueueSource,
    QueueStatus,
    TabletDevice,
)
from apps.users.models import StaffUser

CLINIC_SITE_FIELD_NOT_PROVIDED = object()


def _not_provided():
    """Sentinel for PATCH: field was not in request body."""
    return object()


NOT_PROVIDED = _not_provided()


class InvalidLocaleError(DomainError):
    """Raised when locale for tablet session is unsupported."""


@dataclass(frozen=True)
class IssuedSessionResult:
    """Return payload for newly created session (no token)."""

    session_id: uuid.UUID
    expires_at: timezone.datetime
    intake_form_id: uuid.UUID


@transaction.atomic
def create_clinic_site(
    *,
    code: str,
    name: str,
    is_active: bool = True,
    pdf_import_default_consulting_room_id: uuid.UUID | None = None,
    pdf_import_shift_code: str = QueueShift.FULL_DAY,  # type: ignore[assignment]
) -> ClinicSite:
    """Create a clinic site."""
    if pdf_import_shift_code not in [choice[0] for choice in QueueShift.choices]:
        raise DomainError(
            domain_message(
                "other.domain.invalid_shift_code", value=pdf_import_shift_code
            ),
            api_message_key="other.domain.invalid_shift_code",
            api_message_params={"value": pdf_import_shift_code},
        )
    if pdf_import_default_consulting_room_id is not None:
        raise DomainError(
            domain_message("other.domain.pdf_import_room_after_clinic_create"),
            api_message_key="other.domain.pdf_import_room_after_clinic_create",
        )
    return ClinicSite.objects.create(
        code=code,
        name=name,
        is_active=is_active,
        pdf_import_default_consulting_room_id=pdf_import_default_consulting_room_id,
        pdf_import_shift_code=pdf_import_shift_code,
    )


@transaction.atomic
def update_clinic_site(
    *,
    clinic_site_id: uuid.UUID,
    code: str | None = None,
    name: str | None = None,
    is_active: bool | None = None,
    pdf_import_default_consulting_room_id: (
        uuid.UUID | None | object
    ) = CLINIC_SITE_FIELD_NOT_PROVIDED,
    pdf_import_shift_code: str | object = CLINIC_SITE_FIELD_NOT_PROVIDED,
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
    if pdf_import_default_consulting_room_id is not CLINIC_SITE_FIELD_NOT_PROVIDED:
        if pdf_import_default_consulting_room_id is None:
            site.pdf_import_default_consulting_room = None
        else:
            room = ConsultingRoom.objects.get(id=pdf_import_default_consulting_room_id)
            if room.clinic_site_id != site.id:
                raise DomainError(
                    domain_message("other.domain.consulting_room_wrong_clinic_site"),
                    api_message_key="other.domain.consulting_room_wrong_clinic_site",
                )
            site.pdf_import_default_consulting_room = room
        update_fields.append("pdf_import_default_consulting_room")
    if pdf_import_shift_code is not CLINIC_SITE_FIELD_NOT_PROVIDED:
        if pdf_import_shift_code not in [choice[0] for choice in QueueShift.choices]:
            raise DomainError(
                domain_message(
                    "other.domain.invalid_shift_code", value=pdf_import_shift_code
                ),
                api_message_key="other.domain.invalid_shift_code",
                api_message_params={"value": pdf_import_shift_code},
            )
        site.pdf_import_shift_code = pdf_import_shift_code
        update_fields.append("pdf_import_shift_code")
    if not update_fields:
        raise DomainError(
            domain_message("other.api.provide_field_to_update"),
            api_message_key="other.api.provide_field_to_update",
        )
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
        raise DomainError(
            domain_message("other.api.provide_field_to_update"),
            api_message_key="other.api.provide_field_to_update",
        )
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
def create_tablet_device(
    *,
    android_id: str,
    is_active: bool = True,
    clinic_site_id: uuid.UUID | None = None,
) -> TabletDevice:
    """Create a tablet device (identified by android_id). Optionally assign to a clinic site."""
    return TabletDevice.objects.create(
        android_id=android_id,
        is_active=is_active,
        clinic_site_id=clinic_site_id,
    )


def get_or_create_tablet_device_by_android_id(
    *, android_id: str
) -> tuple[TabletDevice, bool]:
    """Get or create a tablet device by android_id (auto-registration). Returns (device, created).

    New devices have ``clinic_site`` unset; assign a site in admin when isolating queues per site.
    """
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
    clinic_site_id: uuid.UUID | None = NOT_PROVIDED,
) -> TabletDevice:
    """Update mutable tablet fields. Pass clinic_site_id=None to unassign from site."""
    device = TabletDevice.objects.select_for_update().get(id=tablet_device_id)
    update_fields: list[str] = []
    if android_id is not None:
        device.android_id = android_id
        update_fields.append("android_id")
    if is_active is not None:
        device.is_active = is_active
        update_fields.append("is_active")
    if clinic_site_id is not NOT_PROVIDED:
        device.clinic_site_id = clinic_site_id
        update_fields.append("clinic_site_id")
    if not update_fields:
        raise DomainError(
            domain_message("other.api.provide_field_to_update"),
            api_message_key="other.api.provide_field_to_update",
        )
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
    """Set ``last_seen_at`` to now (manual heartbeat from RECEPTION/ADMIN)."""
    device = TabletDevice.objects.select_for_update().get(id=tablet_device_id)
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])
    return device


@transaction.atomic
def record_tablet_login_for_android_id(*, android_id: str) -> TabletDevice:
    """Set ``last_seen_at`` after a successful tablet-area login for this ``android_id``."""
    device, _ = get_or_create_tablet_device_by_android_id(android_id=android_id)
    return mark_tablet_heartbeat(tablet_device_id=device.id)


def _is_supported_locale(locale: str) -> bool:
    normalized = locale.strip().lower()
    return normalized in {"de", "de-de", "en", "en-gb", "en-us", "pl", "pl-pl"}


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
    """Create or update a patient in the manual reception flow."""

    # The actor id is part of the service signature for audit extension in next steps.
    _ = created_or_updated_by_user_id

    from apps.reception.patient_identity import (
        assert_patient_identity_available,
        assert_phone_not_blocked_by_stale_anonymized,
    )

    assert_phone_not_blocked_by_stale_anonymized(
        phone=phone,
        exclude_patient_id=patient_id,
    )
    assert_patient_identity_available(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        date_of_birth=date_of_birth,
        exclude_patient_id=patient_id,
    )

    patient = (
        Patient.objects.select_for_update().filter(id=patient_id).first()
        if patient_id
        else Patient()
    )
    patient.first_name = first_name
    patient.last_name = last_name
    patient.date_of_birth = date_of_birth
    patient.phone = phone
    patient.email = email
    patient.doctolib_patient_id = doctolib_patient_id or None

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
    source: str = QueueSource.MANUAL,  # type: ignore[assignment]
) -> DailyQueue:
    """Create a daily queue for date/site/room/shift. Raises StateTransitionError if slot exists."""
    ClinicSite.objects.get(id=clinic_site_id)
    room = ConsultingRoom.objects.get(id=consulting_room_id)
    if str(room.clinic_site_id) != str(clinic_site_id):
        raise DomainError(
            domain_message("other.domain.consulting_room_wrong_clinic_site"),
            api_message_key="other.domain.consulting_room_wrong_clinic_site",
        )
    if shift_code not in [c[0] for c in QueueShift.choices]:
        raise DomainError(
            domain_message("other.domain.invalid_shift_code", value=shift_code),
            api_message_key="other.domain.invalid_shift_code",
            api_message_params={"value": shift_code},
        )
    if source not in [c[0] for c in QueueSource.choices]:
        raise DomainError(
            domain_message("other.domain.invalid_queue_source", value=source),
            api_message_key="other.domain.invalid_queue_source",
            api_message_params={"value": source},
        )
    if assigned_doctor_id is not None:
        StaffUser.objects.get(id=assigned_doctor_id)
    if DailyQueue.objects.filter(
        queue_date=queue_date,
        clinic_site_id=clinic_site_id,
        consulting_room_id=consulting_room_id,
        shift_code=shift_code,
    ).exists():
        raise StateTransitionError(
            domain_message("other.api.duplicate_queue_slot"),
            api_message_key="other.api.duplicate_queue_slot",
        )
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
        raise DomainError(
            domain_message("other.domain.invalid_queue_status", value=status),
            api_message_key="other.domain.invalid_queue_status",
            api_message_params={"value": status},
        )
    queue = DailyQueue.objects.select_for_update().get(id=daily_queue_id)
    queue.status = status
    queue.save(update_fields=["status", "updated_at"])
    return queue


@transaction.atomic
def update_daily_queue(
    daily_queue_id: uuid.UUID,
    *,
    status: str | None = None,
    assigned_doctor_id: uuid.UUID | None = NOT_PROVIDED,
) -> DailyQueue:
    """Update queue status and/or assigned doctor. At least one must be provided."""
    if status is None and assigned_doctor_id is NOT_PROVIDED:
        raise DomainError(
            domain_message("other.domain.daily_queue_update_requires_fields"),
            api_message_key="other.domain.daily_queue_update_requires_fields",
        )
    if status is not None and status not in [c[0] for c in QueueStatus.choices]:
        raise DomainError(
            domain_message("other.domain.invalid_queue_status", value=status),
            api_message_key="other.domain.invalid_queue_status",
            api_message_params={"value": status},
        )
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
    actor_user_id: uuid.UUID | None = None,
) -> QueueEntry:
    """Update queue entry status and/or notes. DELETE semantic = set CANCELLED.

    ``actor_user_id`` (optional): who initiated the change; used for audit when
    paper intake authorization is auto-revoked on ``CANCELLED``.
    """
    if entry_status is not None and entry_status not in [
        c[0] for c in QueueEntryStatus.choices
    ]:
        raise DomainError(
            domain_message(
                "other.domain.invalid_queue_entry_status", value=entry_status
            ),
            api_message_key="other.domain.invalid_queue_entry_status",
            api_message_params={"value": entry_status},
        )
    entry = QueueEntry.objects.select_for_update(of=("self",)).get(id=queue_entry_id)
    update_fields: list[str] = ["updated_at"]
    if entry_status is not None:
        entry.entry_status = entry_status
        update_fields.append("entry_status")
        if entry_status == QueueEntryStatus.CANCELLED:
            with cogito_business_span(
                "reception.update_queue_entry_cancelled",
                queue_entry_id=entry.id,
                extra_attributes={
                    "cogito.queue_entry_status": entry_status,
                },
            ):
                # Lazy import: keep reception free of ``medical.models`` / paper-intake details.
                from apps.medical.services import (
                    autorevoke_paper_intake_authorization_after_queue_entry_cancelled,
                )

                autorevoke_paper_intake_authorization_after_queue_entry_cancelled(
                    queue_entry_id=entry.id,
                    actor_user_id=actor_user_id,
                )
            entry.doctor_list_sort_at = None
            update_fields.append("doctor_list_sort_at")
    if notes is not None:
        entry.notes = notes
        update_fields.append("notes")
    entry.save(update_fields=update_fields)
    return entry


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
        raise StateTransitionError(
            domain_message("other.domain.queue_closed_cannot_add_patient"),
            api_message_key="other.domain.queue_closed_cannot_add_patient",
        )

    next_position = (
        QueueEntry.objects.select_for_update(of=("self",))
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
        raise DomainError(
            domain_message("other.domain.expires_in_minutes_positive"),
            api_message_key="other.domain.expires_in_minutes_positive",
        )
    if not _is_supported_locale(form_locale):
        raise InvalidLocaleError(
            domain_message("other.domain.unsupported_form_locale", locale=form_locale),
            api_message_key="other.domain.unsupported_form_locale",
            api_message_params={"locale": form_locale},
        )

    queue_entry = QueueEntry.objects.select_for_update(of=("self",)).get(
        id=queue_entry_id
    )

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
