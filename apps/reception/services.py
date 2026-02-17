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
from apps.reception.models import DailyQueue, Patient, PatientFormSession, QueueEntry, QueueStatus, TabletDevice


class InvalidLocaleError(DomainError):
    """Raised when locale for tablet session is unsupported."""


@dataclass(frozen=True)
class IssuedSessionToken:
    """Return payload for newly issued plain token + session metadata."""

    token_plain: str
    session_id: uuid.UUID
    expires_at: timezone.datetime


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
