from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal, TypeAlias

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Max, Prefetch, Q
from django.utils import timezone

from apps.core.api_utils import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    safe_parse_positive_int,
)
from apps.core.domain_messages import domain_message
from apps.core.otel_spans import cogito_business_span
from apps.core.exceptions import (
    DomainError,
    IdempotencyConflictError,
)
from apps.medical.medical_payload_schemas import (
    validate_medical_payload_complete_for_publish,
)
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.intake.services import get_intake_form_context
from apps.medical.models import (
    DocVersionStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
    PaperIntakeAuthorization,
    PdfStatus,
)
from apps.operations.services import create_audit_event
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.services import retry_outbox_event, _try_delete_file
from apps.reception.models import QueueEntry, QueueEntryStatus
from apps.users.models import StaffUser

DOCUMENT_LOCK_TIMEOUT_HOURS = 6

_PAPER_INTAKE_AUTH_REASON_MIN_LEN = 10
_PAPER_INTAKE_AUTH_REASON_MAX_LEN = 500

PaperIntakeAutorevokeTrigger: TypeAlias = Literal[
    "intake_form_submitted",
    "queue_entry_cancelled",
]

PAPER_INTAKE_AUTOREVOKE_TRIGGER_INTAKE_SUBMITTED: PaperIntakeAutorevokeTrigger = (
    "intake_form_submitted"
)
PAPER_INTAKE_AUTOREVOKE_TRIGGER_QUEUE_ENTRY_CANCELLED: PaperIntakeAutorevokeTrigger = (
    "queue_entry_cancelled"
)


def _staff_user_display_name(user: StaffUser | None) -> str:
    if user is None:
        return ""
    name = f"{user.first_name} {user.last_name}".strip()
    return name or (user.username or "")


def _is_admin_or_manager_medical_oversight(user: Any) -> bool:
    """Pełen widok kolejki / dokumentów jak admin (rola Manager = nadzór operacyjny)."""
    return bool(
        getattr(user, "is_admin_role", False) or getattr(user, "is_manager", False)
    )


def get_document_lock_state(
    doc: MedicalDocument, *, now: datetime | None = None
) -> tuple[bool, str | None, datetime | None]:
    """
    Returns (is_effective_lock, locked_by_display_name, locked_at).
    Expired locks are treated as ineffective (False, None, None).
    """
    at = now or timezone.now()
    if not doc.locked_by_user_id or not doc.locked_at:
        return False, None, None
    if doc.locked_at < at - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS):
        return False, None, None
    holder = getattr(doc, "locked_by_user", None)
    if holder is None and doc.locked_by_user_id:
        holder = StaffUser.objects.filter(id=doc.locked_by_user_id).first()
    return True, _staff_user_display_name(holder), doc.locked_at


@transaction.atomic
def acquire_document_lock(
    *, medical_document_id: uuid.UUID, user: Any
) -> tuple[bool, str | None]:
    """
    Acquire or refresh edit lock for a DRAFT document. Published documents are not locked.

    Returns (granted, current_holder_display_name_if_denied).
    Admin may take over an active lock held by another user.
    """
    doc = MedicalDocument.objects.select_for_update().get(id=medical_document_id)
    if doc.status != MedicalDocStatus.DRAFT:
        return True, None

    now = timezone.now()
    cutoff = now - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS)
    locked = (
        doc.locked_by_user_id is not None
        and doc.locked_at is not None
        and doc.locked_at >= cutoff
    )

    if locked:
        if doc.locked_by_user_id == user.id:
            doc.locked_at = now
            doc.save(update_fields=["locked_at", "updated_at"])
            return True, None
        if _is_admin_or_manager_medical_oversight(user):
            doc.locked_by_user_id = user.id
            doc.locked_at = now
            doc.save(update_fields=["locked_by_user", "locked_at", "updated_at"])
            return True, None
        holder = StaffUser.objects.filter(id=doc.locked_by_user_id).first()
        return False, _staff_user_display_name(holder)

    doc.locked_by_user_id = user.id
    doc.locked_at = now
    doc.save(update_fields=["locked_by_user", "locked_at", "updated_at"])
    return True, None


@transaction.atomic
def release_document_lock(*, medical_document_id: uuid.UUID, user: Any) -> bool:
    """
    Clear edit lock if the user holds it, or if the user is admin.
    Returns True if the lock row was cleared or there was nothing to release.
    """
    doc = MedicalDocument.objects.select_for_update().get(id=medical_document_id)
    if not doc.locked_by_user_id:
        return True
    if doc.locked_by_user_id != user.id and not _is_admin_or_manager_medical_oversight(
        user
    ):
        return False
    doc.locked_by_user_id = None
    doc.locked_at = None
    doc.save(update_fields=["locked_by_user", "locked_at", "updated_at"])
    return True


@transaction.atomic
def refresh_document_lock(*, medical_document_id: uuid.UUID, user: Any) -> bool:
    """
    Refresh ``locked_at`` for the current holder (or acquire if lock is free/expired).
    Returns False if another user holds an effective lock (and caller is not admin).
    """
    doc = MedicalDocument.objects.select_for_update().get(id=medical_document_id)
    if doc.status != MedicalDocStatus.DRAFT:
        return True

    now = timezone.now()
    cutoff = now - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS)
    locked = (
        doc.locked_by_user_id is not None
        and doc.locked_at is not None
        and doc.locked_at >= cutoff
    )

    if locked and doc.locked_by_user_id != user.id:
        if _is_admin_or_manager_medical_oversight(user):
            doc.locked_by_user_id = user.id
            doc.locked_at = now
            doc.save(update_fields=["locked_by_user", "locked_at", "updated_at"])
            return True
        return False

    doc.locked_by_user_id = user.id
    doc.locked_at = now
    doc.save(update_fields=["locked_by_user", "locked_at", "updated_at"])
    return True


def assigned_doctor_audit_metadata(medical_document: MedicalDocument) -> dict[str, str]:
    """Expose assigned doctor in audit metadata for GET /audit-events doctor filter."""
    aid = medical_document.queue_entry.daily_queue.assigned_doctor_id
    if aid is None:
        return {}
    return {"assigned_doctor_id": str(aid)}


def outbox_event_stage_status(event: OutboxEvent | None, completed: bool) -> str:
    if completed:
        return "COMPLETED"
    if event is None:
        return "PENDING"
    if event.status in [OutboxStatus.PENDING, OutboxStatus.PROCESSING]:
        return event.status
    if event.status == OutboxStatus.PROCESSED:
        return "COMPLETED"
    return "FAILED"


def latest_retryable_outbox_event(
    version: MedicalDocumentVersion,
) -> OutboxEvent | None:
    """Return retryable event (FAILED/DEAD_LETTER) for version if no stage is currently running."""
    events_by_type = {e.event_type: e for e in version.outbox_events.all()}
    if any(
        e.status in [OutboxStatus.PENDING, OutboxStatus.PROCESSING]
        for e in events_by_type.values()
    ):
        return None
    for event_type in [
        OutboxEventType.SMS_SEND,
        OutboxEventType.HIDRIVE_UPLOAD,
        OutboxEventType.GENERATE_PDF,
    ]:
        event = events_by_type.get(event_type)
        if event and event.status in [OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER]:
            return event
    return None


def latest_version_processing_error_message(
    version: MedicalDocumentVersion,
) -> str | None:
    events = list(version.outbox_events.all())
    failed = [
        e
        for e in events
        if e.status in [OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER]
        and (e.error_message or "").strip()
    ]
    if not failed:
        return None
    failed.sort(key=lambda e: e.updated_at, reverse=True)
    return failed[0].error_message


def check_doctor_document_access(document: MedicalDocument, user: Any) -> None:
    """
    Raise ObjectDoesNotExist if user (doctor) does not have access.
    Access is granted if user is the author OR is assigned to the document's queue.
    Any doctor may access a document in DRAFT (shared work queue for describing).
    ADMIN and Manager (nadzór) have access to all.
    """
    if _is_admin_or_manager_medical_oversight(user):
        return
    if document.created_by_user_id == user.id:
        return
    if document.queue_entry.daily_queue.assigned_doctor_id == user.id:
        return
    if document.status == MedicalDocStatus.DRAFT and getattr(user, "is_doctor", False):
        return
    raise ObjectDoesNotExist("Medical document not found.")


def check_doctor_queue_entry_access(queue_entry: QueueEntry, user: Any) -> None:
    """
    Raise ObjectDoesNotExist if user does not have access to the queue entry.

    Allowed: admin or manager; doctor assigned to the daily queue; creator of an existing
    medical document for this entry; any doctor when there is no document yet
    or the document is still DRAFT (shared queue).
    """
    if _is_admin_or_manager_medical_oversight(user):
        return
    if queue_entry.daily_queue.assigned_doctor_id == user.id:
        return
    md = MedicalDocument.objects.filter(queue_entry_id=queue_entry.id).first()
    if md is not None:
        if md.created_by_user_id == user.id:
            return
        if md.status == MedicalDocStatus.DRAFT and getattr(user, "is_doctor", False):
            return
    elif getattr(user, "is_doctor", False):
        return
    raise ObjectDoesNotExist("Queue entry not found.")


def create_or_get_medical_document(
    *,
    queue_entry_id: uuid.UUID,
    intake_form_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
) -> MedicalDocument:
    """Create medical document for queue entry if not existing.

    Intake must be **SUBMITTED** (final). If reception has reopened the intake
    (**REOPENED**, patient editing again), creation is blocked until the form is
    submitted again — avoids Befund against a changing intake snapshot.
    """
    QueueEntry.objects.get(id=queue_entry_id)
    intake_form = PatientIntakeForm.objects.get(id=intake_form_id)
    if intake_form.queue_entry_id != queue_entry_id:
        raise DomainError(
            domain_message("other.domain.intake_form_wrong_queue_entry"),
            api_message_key="other.domain.intake_form_wrong_queue_entry",
        )
    if intake_form.form_status != IntakeStatus.SUBMITTED:
        raise DomainError(
            domain_message("other.domain.intake_form_must_be_submitted"),
            api_message_key="other.domain.intake_form_must_be_submitted",
        )
    medical_document, created = MedicalDocument.objects.get_or_create(
        queue_entry_id=queue_entry_id,
        defaults={
            "intake_form_id": intake_form_id,
            "created_by_user_id": created_by_user_id,
            "updated_by_user_id": created_by_user_id,
        },
    )
    doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
        id=medical_document.id
    )
    if created:
        meta = {
            "queue_entry_id": str(queue_entry_id),
            "intake_form_id": str(intake_form_id),
            **assigned_doctor_audit_metadata(doc),
        }
        create_audit_event(
            event_type="MEDICAL_DOCUMENT_CREATED",
            actor_user_id=created_by_user_id,
            patient_id=doc.queue_entry.patient_id,
            medical_document_id=doc.id,
            context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
            metadata=meta,
        )
    return doc


def _validate_paper_intake_authorization_reason(reason: str) -> str:
    text = (reason or "").strip()
    if len(text) < _PAPER_INTAKE_AUTH_REASON_MIN_LEN:
        raise DomainError(
            domain_message("other.api.paper_intake_authorization_reason_required"),
            api_message_key="other.api.paper_intake_authorization_reason_required",
        )
    if len(text) > _PAPER_INTAKE_AUTH_REASON_MAX_LEN:
        raise DomainError(
            domain_message("other.api.paper_intake_authorization_reason_too_long"),
            api_message_key="other.api.paper_intake_authorization_reason_too_long",
        )
    return text


@transaction.atomic
def authorize_paper_intake(
    *,
    queue_entry_id: uuid.UUID,
    authorized_by_user_id: uuid.UUID,
    reason: str,
) -> PaperIntakeAuthorization:
    """ADMIN/MANAGER: authorize paper-intake path for a WAITING entry (does not flip entry_status)."""
    try:
        actor = StaffUser.objects.get(id=authorized_by_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    if not (actor.is_admin_role or actor.is_manager):
        raise DomainError(
            domain_message("other.domain.paper_intake_authorization_invalid_role"),
            api_message_key="other.domain.paper_intake_authorization_invalid_role",
        )
    validated_reason = _validate_paper_intake_authorization_reason(reason)

    with cogito_business_span(
        "medical.authorize_paper_intake",
        queue_entry_id=queue_entry_id,
        audit_event_type="PAPER_INTAKE_AUTHORIZED",
    ) as span:
        try:
            entry = (
                QueueEntry.objects.select_for_update(of=("self",))
                .select_related("daily_queue", "patient")
                .get(id=queue_entry_id)
            )
        except QueueEntry.DoesNotExist as exc:
            raise DomainError(
                domain_message("other.api.queue_entry_not_found"),
                api_message_key="other.api.queue_entry_not_found",
            ) from exc

        if entry.entry_status != QueueEntryStatus.WAITING:
            raise DomainError(
                domain_message(
                    "other.domain.paper_intake_authorization_invalid_status"
                ),
                api_message_key="other.domain.paper_intake_authorization_invalid_status",
            )
        if entry.appointment_time is None:
            raise DomainError(
                domain_message("other.domain.paper_intake_requires_appointment_time"),
                api_message_key="other.domain.paper_intake_requires_appointment_time",
            )
        if timezone.now() < entry.appointment_time + timedelta(hours=3):
            raise DomainError(
                domain_message("other.domain.paper_intake_authorization_too_early"),
                api_message_key="other.domain.paper_intake_authorization_too_early",
            )
        if MedicalDocument.objects.filter(queue_entry_id=entry.id).exists():
            raise DomainError(
                domain_message(
                    "other.domain.medical_document_already_exists_for_queue_entry"
                ),
                api_message_key="other.domain.medical_document_already_exists_for_queue_entry",
            )
        intake_row = (
            PatientIntakeForm.objects.filter(queue_entry_id=entry.id)
            .only("id", "form_status")
            .first()
        )
        if intake_row is not None and intake_row.form_status == IntakeStatus.SUBMITTED:
            raise DomainError(
                domain_message(
                    "other.domain.paper_intake_authorization_intake_form_submitted"
                ),
                api_message_key="other.domain.paper_intake_authorization_intake_form_submitted",
            )
        if PaperIntakeAuthorization.objects.filter(queue_entry_id=entry.id).exists():
            raise DomainError(
                domain_message(
                    "other.domain.paper_intake_authorization_already_exists"
                ),
                api_message_key="other.domain.paper_intake_authorization_already_exists",
            )

        now = timezone.now()
        authorization = PaperIntakeAuthorization.objects.create(
            queue_entry=entry,
            authorized_at=now,
            authorized_by_id=authorized_by_user_id,
            reason=validated_reason,
        )
        entry.doctor_list_sort_at = now
        entry.save(update_fields=["doctor_list_sort_at", "updated_at"])

        intake_status = intake_row.form_status if intake_row is not None else None
        create_audit_event(
            event_type="PAPER_INTAKE_AUTHORIZED",
            actor_user_id=authorized_by_user_id,
            patient_id=entry.patient_id,
            context_clinic_site_id=entry.daily_queue.clinic_site_id,
            metadata={
                "queue_entry_id": str(entry.id),
                "authorization_id": str(authorization.id),
                "authorization_reason": validated_reason,
                "appointment_time": entry.appointment_time.isoformat(),
                "intake_form_id_at_authorization": (
                    str(intake_row.id) if intake_row is not None else None
                ),
                "intake_form_status_at_authorization": intake_status,
            },
        )
        if span.is_recording():
            span.set_attribute(
                "cogito.paper_intake_authorization_id", str(authorization.id)
            )
        return authorization


@transaction.atomic
def create_medical_document_without_intake(
    *,
    queue_entry_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
) -> MedicalDocument:
    """DOCTOR/ADMIN/MANAGER: create PAPER_INTAKE document after manager paper authorization (T2)."""
    try:
        creator = StaffUser.objects.get(id=created_by_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    if not (creator.is_doctor or creator.is_admin_role or creator.is_manager):
        raise DomainError(
            domain_message("other.domain.paper_intake_create_document_invalid_role"),
            api_message_key="other.domain.paper_intake_create_document_invalid_role",
        )

    with cogito_business_span(
        "medical.create_medical_document_without_intake",
        queue_entry_id=queue_entry_id,
        audit_event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
    ) as span:
        try:
            queue_entry = (
                QueueEntry.objects.select_for_update(of=("self",))
                .select_related("daily_queue", "patient")
                .get(id=queue_entry_id)
            )
        except QueueEntry.DoesNotExist as exc:
            raise DomainError(
                domain_message("other.api.queue_entry_not_found"),
                api_message_key="other.api.queue_entry_not_found",
            ) from exc

        if queue_entry.entry_status != QueueEntryStatus.WAITING:
            raise DomainError(
                domain_message(
                    "other.domain.queue_entry_must_be_waiting_for_paper_intake"
                ),
                api_message_key="other.domain.queue_entry_must_be_waiting_for_paper_intake",
            )
        if queue_entry.appointment_time is None:
            raise DomainError(
                domain_message("other.domain.paper_intake_requires_appointment_time"),
                api_message_key="other.domain.paper_intake_requires_appointment_time",
            )
        if timezone.now() < queue_entry.appointment_time + timedelta(hours=3):
            raise DomainError(
                domain_message("other.domain.paper_intake_earliest_after_appointment"),
                api_message_key="other.domain.paper_intake_earliest_after_appointment",
            )

        if MedicalDocument.objects.filter(queue_entry_id=queue_entry.id).exists():
            raise DomainError(
                domain_message(
                    "other.domain.medical_document_already_exists_for_queue_entry"
                ),
                api_message_key="other.domain.medical_document_already_exists_for_queue_entry",
            )

        intake_row = (
            PatientIntakeForm.objects.filter(queue_entry_id=queue_entry.id)
            .only("form_status")
            .first()
        )
        if intake_row is not None and intake_row.form_status == IntakeStatus.SUBMITTED:
            raise DomainError(
                domain_message(
                    "other.domain.paper_intake_intake_form_appeared_after_authorization"
                ),
                api_message_key="other.domain.paper_intake_intake_form_appeared_after_authorization",
            )

        try:
            auth = (
                PaperIntakeAuthorization.objects.select_for_update()
                .select_related("authorized_by")
                .get(queue_entry_id=queue_entry.id)
            )
        except PaperIntakeAuthorization.DoesNotExist as exc:
            raise DomainError(
                domain_message("other.domain.paper_intake_not_authorized"),
                api_message_key="other.domain.paper_intake_not_authorized",
            ) from exc

        snap_id = auth.id
        snap_reason = auth.reason
        snap_by_id = auth.authorized_by_id
        snap_at = auth.authorized_at
        snap_age_seconds = (timezone.now() - snap_at).total_seconds()

        try:
            medical_document = MedicalDocument.objects.create(
                queue_entry_id=queue_entry.id,
                intake_form_id=None,
                source_type=MedicalDocumentSourceType.PAPER_INTAKE,
                created_by_user_id=created_by_user_id,
                updated_by_user_id=created_by_user_id,
            )
        except IntegrityError as exc:
            raise DomainError(
                domain_message(
                    "other.domain.medical_document_already_exists_for_queue_entry"
                ),
                api_message_key="other.domain.medical_document_already_exists_for_queue_entry",
            ) from exc

        status_before = queue_entry.entry_status
        now = timezone.now()
        queue_entry.entry_status = QueueEntryStatus.PAPER_INTAKE_COMPLETED
        # UX: fresh paper document should sort like a new row (overrides authorize-time stamp).
        queue_entry.doctor_list_sort_at = now
        queue_entry.save(
            update_fields=["entry_status", "doctor_list_sort_at", "updated_at"]
        )

        PaperIntakeAuthorization.objects.filter(id=snap_id).delete()

        create_audit_event(
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
            actor_user_id=created_by_user_id,
            patient_id=queue_entry.patient_id,
            medical_document_id=medical_document.id,
            context_clinic_site_id=queue_entry.daily_queue.clinic_site_id,
            metadata={
                "queue_entry_id": str(queue_entry.id),
                "intake_form_id": None,
                "source_type": MedicalDocumentSourceType.PAPER_INTAKE,
                "queue_entry_status_before": status_before,
                "queue_entry_status_after": queue_entry.entry_status,
                "paper_intake_authorization_id": str(snap_id),
                "paper_intake_authorization_reason_snapshot": snap_reason,
                "paper_intake_authorized_by_id": str(snap_by_id),
                "paper_intake_authorized_at": snap_at.isoformat(),
                "paper_intake_authorization_age_seconds": snap_age_seconds,
                **assigned_doctor_audit_metadata(medical_document),
            },
        )
        if span.is_recording():
            span.set_attribute("cogito.medical_document_id", str(medical_document.id))
        return medical_document


@transaction.atomic
def revoke_paper_intake_authorization(
    *,
    queue_entry_id: uuid.UUID,
    revoked_by_user_id: uuid.UUID,
    reason: str,
) -> None:
    """Remove an active paper intake authorization (ADMIN/MANAGER). Audits the snapshot."""
    try:
        actor = StaffUser.objects.get(id=revoked_by_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    if not (actor.is_admin_role or actor.is_manager):
        raise DomainError(
            domain_message("other.domain.paper_intake_authorization_invalid_role"),
            api_message_key="other.domain.paper_intake_authorization_invalid_role",
        )
    validated_reason = _validate_paper_intake_authorization_reason(reason)

    with cogito_business_span(
        "medical.revoke_paper_intake_authorization",
        queue_entry_id=queue_entry_id,
        audit_event_type="PAPER_INTAKE_AUTHORIZATION_REVOKED",
    ) as span:
        try:
            entry = (
                QueueEntry.objects.select_for_update(of=("self",))
                .select_related("daily_queue", "patient")
                .get(id=queue_entry_id)
            )
        except QueueEntry.DoesNotExist as exc:
            raise DomainError(
                domain_message("other.api.queue_entry_not_found"),
                api_message_key="other.api.queue_entry_not_found",
            ) from exc

        try:
            auth = (
                PaperIntakeAuthorization.objects.select_for_update()
                .select_related("authorized_by")
                .get(queue_entry_id=entry.id)
            )
        except PaperIntakeAuthorization.DoesNotExist as exc:
            raise DomainError(
                domain_message("other.domain.paper_intake_authorization_not_found"),
                api_message_key="other.domain.paper_intake_authorization_not_found",
            ) from exc

        if MedicalDocument.objects.filter(queue_entry_id=entry.id).exists():
            raise DomainError(
                domain_message(
                    "other.domain.paper_intake_revoke_after_document_created"
                ),
                api_message_key="other.domain.paper_intake_revoke_after_document_created",
            )

        snapshot_id = auth.id
        snapshot_by_id = auth.authorized_by_id
        snapshot_at = auth.authorized_at
        snapshot_auth_reason = auth.reason

        auth.delete()

        entry.doctor_list_sort_at = None
        entry.save(update_fields=["doctor_list_sort_at", "updated_at"])

        create_audit_event(
            event_type="PAPER_INTAKE_AUTHORIZATION_REVOKED",
            actor_user_id=revoked_by_user_id,
            patient_id=entry.patient_id,
            context_clinic_site_id=entry.daily_queue.clinic_site_id,
            metadata={
                "queue_entry_id": str(entry.id),
                "revoke_reason": validated_reason,
                "previous_authorization_id": str(snapshot_id),
                "previously_authorized_by_id": str(snapshot_by_id),
                "previously_authorized_at": snapshot_at.isoformat(),
                "previous_authorization_reason": snapshot_auth_reason,
            },
        )
        if span.is_recording():
            span.set_attribute("cogito.paper_intake_authorization_id", str(snapshot_id))


def _autorevoke_paper_intake_authorization_if_present(
    *,
    queue_entry_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    trigger: PaperIntakeAutorevokeTrigger,
    extra_audit_metadata: dict[str, Any] | None = None,
) -> None:
    """Delete active paper auth for ``queue_entry_id`` if any; audit or no-op.

    Caller must run inside ``transaction.atomic`` and already hold
    ``select_for_update`` on the related ``QueueEntry`` (lock order: entry, then
    this row) to avoid deadlocks with other paper-intake flows.
    """
    with cogito_business_span(
        "medical.autorevoke_paper_intake_authorization",
        queue_entry_id=queue_entry_id,
        audit_event_type="PAPER_INTAKE_AUTHORIZATION_AUTOREVOKED",
        extra_attributes={"cogito.paper_intake_autorevoke_trigger": trigger},
    ) as span:
        try:
            paper_auth = (
                PaperIntakeAuthorization.objects.select_for_update()
                .select_related("queue_entry", "queue_entry__daily_queue")
                .get(queue_entry_id=queue_entry_id)
            )
        except PaperIntakeAuthorization.DoesNotExist:
            if span.is_recording():
                span.set_attribute("cogito.paper_intake_authorization_removed", False)
            return
        entry = paper_auth.queue_entry
        prev = {
            "id": str(paper_auth.id),
            "authorized_by_id": str(paper_auth.authorized_by_id),
            "authorized_at": paper_auth.authorized_at.isoformat(),
            "reason": paper_auth.reason,
        }
        paper_auth.delete()
        metadata: dict[str, Any] = {
            "queue_entry_id": str(entry.id),
            "trigger": trigger,
            "previous_authorization": prev,
        }
        if extra_audit_metadata:
            metadata.update(extra_audit_metadata)
        create_audit_event(
            event_type="PAPER_INTAKE_AUTHORIZATION_AUTOREVOKED",
            actor_user_id=actor_user_id,
            patient_id=entry.patient_id,
            context_clinic_site_id=entry.daily_queue.clinic_site_id,
            metadata=metadata,
        )
        if span.is_recording():
            span.set_attribute("cogito.paper_intake_authorization_removed", True)


def autorevoke_paper_intake_authorization_after_intake_submit(
    *,
    queue_entry_id: uuid.UUID,
    intake_form_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    """
    Remove paper-intake authorization when the patient submits digital intake.

    Must run inside the caller's ``transaction.atomic`` (e.g. ``submit_patient_intake_form``).
    Intentionally **not** wrapped in ``@transaction.atomic`` here to avoid nested blocks.
    """
    _autorevoke_paper_intake_authorization_if_present(
        queue_entry_id=queue_entry_id,
        actor_user_id=actor_user_id,
        trigger=PAPER_INTAKE_AUTOREVOKE_TRIGGER_INTAKE_SUBMITTED,
        extra_audit_metadata={"intake_form_id": str(intake_form_id)},
    )


def autorevoke_paper_intake_authorization_after_queue_entry_cancelled(
    *,
    queue_entry_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    """
    Remove paper-intake authorization when a queue entry is cancelled.

    Must run inside the caller's ``transaction.atomic`` (e.g. ``update_queue_entry``)
    with the ``QueueEntry`` row already locked via ``select_for_update``.
    Intentionally **not** wrapped in ``@transaction.atomic`` here.
    """
    _autorevoke_paper_intake_authorization_if_present(
        queue_entry_id=queue_entry_id,
        actor_user_id=actor_user_id,
        trigger=PAPER_INTAKE_AUTOREVOKE_TRIGGER_QUEUE_ENTRY_CANCELLED,
    )


SAVE_DRAFT_INTENT_EDIT = "edit"
SAVE_DRAFT_INTENT_AMEND = "amend"
_VALID_SAVE_DRAFT_INTENTS = frozenset({SAVE_DRAFT_INTENT_EDIT, SAVE_DRAFT_INTENT_AMEND})


@transaction.atomic
def save_draft_document_version(
    *,
    medical_document_id: uuid.UUID,
    updated_by_user_id: uuid.UUID,
    medical_payload_schema_version: int = 1,
    medical_payload: dict,
    diagnosis_code: str | None = None,
    procedure_code: str | None = None,
    intent: str = SAVE_DRAFT_INTENT_EDIT,
) -> MedicalDocumentVersion:
    """
    Save draft payload for a medical document.

    - If the document is in DRAFT and the latest version is DRAFT, the latest
      DRAFT version is updated in place. ``intent`` is ignored here.
    - If the document is in DRAFT and there is no DRAFT version yet (e.g. only
      a previously DRAFT-revoked or initial state), a new DRAFT version is
      created and ``current_version_no`` advances. ``intent`` is ignored.
    - If the document is in PUBLISHED status, ``intent`` MUST be
      ``"amend"``. The function then creates a new DRAFT version with
      ``version_no = max_published_version_no + 1`` (or updates the existing
      pending DRAFT in place on subsequent saves), keeps
      ``MedicalDocument.status = PUBLISHED`` and only flips
      ``has_pending_revision = True``. ``current_version_no`` does NOT advance –
      the patient still sees ``published_version_no`` until the doctor
      republishes or discards.
    - If the document is PUBLISHED but ``intent != "amend"``, raises
      ``DomainError("other.api.amend_intent_required")``. The API layer turns
      this into HTTP 409 to make accidental reverts impossible from any path
      (UI, retries, scripts).
    """
    if intent not in _VALID_SAVE_DRAFT_INTENTS:
        raise DomainError(
            domain_message("other.api.invalid_save_draft_intent"),
            api_message_key="other.api.invalid_save_draft_intent",
        )

    medical_document = MedicalDocument.objects.select_for_update().get(
        id=medical_document_id
    )

    latest_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(medical_document_id=medical_document_id)
        .order_by("-version_no")
        .first()
    )

    is_published_doc = medical_document.status == MedicalDocStatus.PUBLISHED
    if is_published_doc and intent != SAVE_DRAFT_INTENT_AMEND:
        raise DomainError(
            domain_message("other.api.amend_intent_required"),
            api_message_key="other.api.amend_intent_required",
        )

    if latest_version and latest_version.version_status == DocVersionStatus.PUBLISHED:
        if latest_version.local_pdf_deleted_at is not None:
            raise DomainError(
                domain_message("other.domain.republish_after_retention_not_allowed"),
                api_message_key="other.domain.republish_after_retention_not_allowed",
            )

    if latest_version and latest_version.version_status == DocVersionStatus.DRAFT:
        latest_version.medical_payload_schema_version = medical_payload_schema_version
        latest_version.medical_payload = medical_payload
        latest_version.diagnosis_code = diagnosis_code
        latest_version.procedure_code = procedure_code
        latest_version.save(
            update_fields=[
                "medical_payload_schema_version",
                "medical_payload",
                "diagnosis_code",
                "procedure_code",
            ]
        )
        medical_document.updated_by_user_id = updated_by_user_id
        medical_document.save(update_fields=["updated_by_user", "updated_at"])
        create_audit_event(
            event_type="DOCUMENT_DRAFT_SAVED",
            actor_user_id=updated_by_user_id,
            patient_id=medical_document.queue_entry.patient_id,
            medical_document_id=medical_document.id,
            context_clinic_site_id=medical_document.queue_entry.daily_queue.clinic_site_id,
            metadata={
                "medical_document_version_id": str(latest_version.id),
                "version_no": latest_version.version_no,
                "mode": "update",
                "intent": intent,
                "is_revision_of_published": medical_document.has_pending_revision,
                **assigned_doctor_audit_metadata(medical_document),
            },
        )
        return latest_version

    next_version_no = (
        MedicalDocumentVersion.objects.filter(
            medical_document_id=medical_document_id
        ).aggregate(max_no=Max("version_no"))["max_no"]
        or 0
    ) + 1

    created_version = MedicalDocumentVersion.objects.create(
        medical_document_id=medical_document_id,
        version_no=next_version_no,
        version_status=DocVersionStatus.DRAFT,
        medical_payload_schema_version=medical_payload_schema_version,
        medical_payload=medical_payload,
        diagnosis_code=diagnosis_code,
        procedure_code=procedure_code,
    )

    medical_document.updated_by_user_id = updated_by_user_id
    if is_published_doc:
        # Amend mode: keep status PUBLISHED, do NOT advance current_version_no
        # (the patient still sees published_version_no), only mark pending revision.
        medical_document.has_pending_revision = True
        medical_document.save(
            update_fields=[
                "has_pending_revision",
                "updated_by_user",
                "updated_at",
            ]
        )
        create_audit_event(
            event_type="DOCUMENT_REVISION_STARTED",
            actor_user_id=updated_by_user_id,
            patient_id=medical_document.queue_entry.patient_id,
            medical_document_id=medical_document.id,
            context_clinic_site_id=medical_document.queue_entry.daily_queue.clinic_site_id,
            metadata={
                "medical_document_version_id": str(created_version.id),
                "version_no": created_version.version_no,
                "previous_published_version_no": medical_document.published_version_no,
                **assigned_doctor_audit_metadata(medical_document),
            },
        )
    else:
        medical_document.current_version_no = created_version.version_no
        medical_document.status = MedicalDocStatus.DRAFT
        medical_document.save(
            update_fields=[
                "current_version_no",
                "status",
                "updated_by_user",
                "updated_at",
            ]
        )

    create_audit_event(
        event_type="DOCUMENT_DRAFT_SAVED",
        actor_user_id=updated_by_user_id,
        patient_id=medical_document.queue_entry.patient_id,
        medical_document_id=medical_document.id,
        context_clinic_site_id=medical_document.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "medical_document_version_id": str(created_version.id),
            "version_no": created_version.version_no,
            "mode": "create",
            "intent": intent,
            "is_revision_of_published": is_published_doc,
            **assigned_doctor_audit_metadata(medical_document),
        },
    )
    return created_version


@transaction.atomic
def discard_pending_revision(
    *,
    medical_document_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> MedicalDocument:
    """
    Discard a pending DRAFT revision on a PUBLISHED document.

    Effect:
    - delete the latest DRAFT version. Related ``OutboxEvent`` rows use
      ``ForeignKey(..., on_delete=CASCADE)`` to the version (see ``outbox`` app),
      so they are removed with the version; keep this in mind if new FKs to
      ``MedicalDocumentVersion`` are added without CASCADE.
    - clear ``has_pending_revision``,
    - leave ``current_version_no`` and ``published_version_no`` untouched,
    - emit ``DOCUMENT_REVISION_DISCARDED`` audit event.

    If there is no pending revision, raises ``DomainError`` so the caller can
    return HTTP 409 (or 404, depending on framing). The decision: 409 with
    ``other.api.no_pending_revision_to_discard``.
    """
    medical_document = MedicalDocument.objects.select_for_update().get(
        id=medical_document_id
    )
    if not medical_document.has_pending_revision:
        raise DomainError(
            domain_message("other.api.no_pending_revision_to_discard"),
            api_message_key="other.api.no_pending_revision_to_discard",
        )
    pending = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.DRAFT,
        )
        .order_by("-version_no")
        .first()
    )
    if pending is None:
        # Defensive: flag was set but no draft exists – just clear the flag.
        medical_document.has_pending_revision = False
        medical_document.save(update_fields=["has_pending_revision", "updated_at"])
        return medical_document

    discarded_version_no = pending.version_no
    discarded_version_id = pending.id
    pending.delete()

    medical_document.has_pending_revision = False
    medical_document.updated_by_user_id = actor_user_id
    medical_document.locked_by_user_id = None
    medical_document.locked_at = None
    medical_document.save(
        update_fields=[
            "has_pending_revision",
            "updated_by_user",
            "updated_at",
            "locked_by_user",
            "locked_at",
        ]
    )
    create_audit_event(
        event_type="DOCUMENT_REVISION_DISCARDED",
        actor_user_id=actor_user_id,
        patient_id=medical_document.queue_entry.patient_id,
        medical_document_id=medical_document.id,
        context_clinic_site_id=medical_document.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "discarded_version_no": discarded_version_no,
            "discarded_version_id": str(discarded_version_id),
            "published_version_no": medical_document.published_version_no,
            **assigned_doctor_audit_metadata(medical_document),
        },
    )
    return medical_document


@transaction.atomic
def publish_document_version(
    *,
    medical_document_id: uuid.UUID,
    publish_request_id: uuid.UUID,
    published_by_user_id: uuid.UUID,
    publish_locale: str,
    resend_sms: bool = False,
    now: datetime | None = None,
) -> MedicalDocumentVersion:
    """
    Publish latest draft version and enqueue outbox chain idempotently.

    Idempotency rules:
    - same `publish_request_id` returns the already published version;
    - if publication for this document is already in progress, return that version;
    - otherwise publish latest draft and enqueue `GENERATE_PDF`.
    """
    if not publish_request_id:
        raise IdempotencyConflictError(
            domain_message("other.api.publish_request_id_required"),
            api_message_key="other.api.publish_request_id_required",
        )
    if not publish_locale:
        raise DomainError(
            domain_message("other.domain.publish_locale_required"),
            api_message_key="other.domain.publish_locale_required",
        )

    requested_at = now or timezone.now()
    medical_document = MedicalDocument.objects.select_for_update().get(
        id=medical_document_id
    )

    same_request_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            publish_request_id=publish_request_id,
        )
        .first()
    )
    if same_request_version:
        if (
            same_request_version.publish_locale
            and same_request_version.publish_locale != publish_locale
        ):
            raise IdempotencyConflictError(
                domain_message("other.api.publish_request_id_locale_conflict"),
                api_message_key="other.api.publish_request_id_locale_conflict",
            )
        return same_request_version

    in_progress_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.PUBLISHED,
            outbox_events__event_type=OutboxEventType.GENERATE_PDF,
            outbox_events__status__in=[
                OutboxStatus.PENDING,
                OutboxStatus.PROCESSING,
                OutboxStatus.FAILED,
            ],
        )
        .order_by("-version_no")
        .first()
    )
    latest_draft_version_no = MedicalDocumentVersion.objects.filter(
        medical_document_id=medical_document_id,
        version_status=DocVersionStatus.DRAFT,
    ).aggregate(max_no=Max("version_no"))["max_no"]
    if in_progress_version and (
        latest_draft_version_no is None
        or in_progress_version.version_no >= latest_draft_version_no
    ):
        return in_progress_version

    draft_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.DRAFT,
        )
        .order_by("-version_no")
        .first()
    )
    if not draft_version:
        raise DomainError(
            domain_message("other.api.no_draft_before_publish"),
            api_message_key="other.api.no_draft_before_publish",
        )

    validate_medical_payload_complete_for_publish(
        draft_version.medical_payload, locale=publish_locale
    )

    draft_version.version_status = DocVersionStatus.PUBLISHED
    draft_version.publish_request_id = publish_request_id
    draft_version.publish_requested_by_user_id = published_by_user_id
    draft_version.publish_locale = publish_locale
    draft_version.published_by_user_id = published_by_user_id
    draft_version.published_at = requested_at
    draft_version.pdf_generation_status = PdfStatus.PENDING
    draft_version.save(
        update_fields=[
            "version_status",
            "publish_request_id",
            "publish_requested_by_user",
            "publish_locale",
            "published_by_user",
            "published_at",
            "pdf_generation_status",
        ]
    )

    is_republish = (
        medical_document.published_version_no is not None
        and medical_document.published_version_no < draft_version.version_no
    )
    previous_published_version_no = medical_document.published_version_no

    medical_document.status = MedicalDocStatus.PUBLISHED
    medical_document.current_version_no = draft_version.version_no
    medical_document.published_version_no = draft_version.version_no
    medical_document.has_pending_revision = False
    medical_document.last_published_at = requested_at
    medical_document.updated_by_user_id = published_by_user_id
    medical_document.locked_by_user_id = None
    medical_document.locked_at = None
    medical_document.save(
        update_fields=[
            "status",
            "current_version_no",
            "published_version_no",
            "has_pending_revision",
            "last_published_at",
            "updated_by_user",
            "updated_at",
            "locked_by_user",
            "locked_at",
        ]
    )

    OutboxEvent.objects.get_or_create(
        medical_document_version=draft_version,
        event_type=OutboxEventType.GENERATE_PDF,
        defaults={
            "aggregate_id": draft_version.id,
            "payload_schema_version": 1,
            "payload": {
                "medical_document_id": str(medical_document.id),
                "medical_document_version_id": str(draft_version.id),
                "publish_request_id": str(publish_request_id),
                "publish_locale": publish_locale,
                "resend_sms": resend_sms,
            },
            "status": OutboxStatus.PENDING,
        },
    )
    create_audit_event(
        event_type="DOCUMENT_PUBLISHED",
        actor_user_id=published_by_user_id,
        patient_id=medical_document.queue_entry.patient_id,
        medical_document_id=medical_document.id,
        context_clinic_site_id=medical_document.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "medical_document_version_id": str(draft_version.id),
            "version_no": draft_version.version_no,
            "publish_request_id": str(publish_request_id),
            "publish_locale": publish_locale,
            "is_republish": is_republish,
            "previous_published_version_no": previous_published_version_no,
            **assigned_doctor_audit_metadata(medical_document),
        },
    )
    if is_republish:
        create_audit_event(
            event_type="DOCUMENT_REPUBLISHED",
            actor_user_id=published_by_user_id,
            patient_id=medical_document.queue_entry.patient_id,
            medical_document_id=medical_document.id,
            context_clinic_site_id=medical_document.queue_entry.daily_queue.clinic_site_id,
            metadata={
                "medical_document_version_id": str(draft_version.id),
                "new_published_version_no": draft_version.version_no,
                "previous_published_version_no": previous_published_version_no,
                "publish_request_id": str(publish_request_id),
                **assigned_doctor_audit_metadata(medical_document),
            },
        )
    return draft_version


@transaction.atomic
def revoke_document_version(
    *,
    medical_document_id: uuid.UUID,
    revoked_by_user_id: uuid.UUID,
) -> MedicalDocumentVersion:
    """
    Revoke the current published version. Deletes local PDF, sets revoked_at.
    Patient will no longer see or download the document in ergebnisse portal.
    """
    medical_document = (
        MedicalDocument.objects.select_for_update()
        .select_related(
            "queue_entry",
            "queue_entry__daily_queue",
        )
        .get(id=medical_document_id)
    )

    current_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.PUBLISHED,
            version_no=medical_document.current_version_no,
        )
        .select_related(
            "medical_document",
            "medical_document__queue_entry",
            "medical_document__queue_entry__daily_queue",
        )
        .first()
    )
    if not current_version:
        raise DomainError(
            domain_message("other.domain.no_published_version_to_revoke"),
            api_message_key="other.domain.no_published_version_to_revoke",
        )

    if current_version.revoked_at:
        return current_version

    if not (current_version.hidrive_sent and current_version.sms_sent):
        raise DomainError(
            domain_message("other.domain.revoke_requires_full_delivery"),
            api_message_key="other.domain.revoke_requires_full_delivery",
        )

    now = timezone.now()
    _try_delete_file(current_version.pdf_local_path)

    current_version.revoked_at = now
    current_version.pdf_local_path = None
    current_version.local_pdf_deleted_at = now
    update_fields = [
        "revoked_at",
        "pdf_local_path",
        "local_pdf_deleted_at",
    ]

    current_version.save(update_fields=update_fields)

    create_audit_event(
        event_type="DOCUMENT_REVOKED",
        actor_user_id=revoked_by_user_id,
        patient_id=medical_document.queue_entry.patient_id,
        medical_document_id=medical_document.id,
        context_clinic_site_id=medical_document.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "medical_document_version_id": str(current_version.id),
            "version_no": current_version.version_no,
            **assigned_doctor_audit_metadata(medical_document),
        },
    )
    return current_version


def parse_medical_documents_list_params(get_params: Any) -> dict[str, Any]:
    """
    Parse GET parameters for medical documents list (work queue).
    Returns dict with status, queue_date, patient_search, scope, page, page_size.
    """
    status = get_params.get("status") or None
    queue_date = None
    if get_params.get("queue_date"):
        try:
            queue_date = datetime.strptime(
                get_params.get("queue_date", "") or "", "%Y-%m-%d"
            ).date()
        except (ValueError, TypeError):
            pass
    patient_search = get_params.get("patient_search") or None
    scope = (get_params.get("scope") or "all").strip()
    if scope not in {"all", "mine", "published_by_me", "in_revision"}:
        scope = "all"
    page = safe_parse_positive_int(get_params.get("page"), default=1, maximum=10_000)
    page_size = safe_parse_positive_int(
        get_params.get("page_size"),
        default=DEFAULT_LIST_LIMIT,
        maximum=MAX_LIST_LIMIT,
    )
    return {
        "status": status,
        "queue_date": queue_date,
        "patient_search": patient_search,
        "scope": scope,
        "page": page,
        "page_size": page_size,
    }


def list_medical_documents(
    *,
    status: str | None = None,
    queue_date: date | None = None,
    patient_search: str | None = None,
    scope: str = "all",
    user: Any = None,
    page: int = 1,
    page_size: int = DEFAULT_LIST_LIMIT,
) -> tuple[list[MedicalDocument], int]:
    """
    List medical documents for doctor work queue.
    If user is DOCTOR (not admin), returns documents where user is author OR assigned
    to queue, plus every document still in DRAFT (shared describing queue).
    ``scope``:
    - ``all`` / ``mine`` / ``published_by_me``: parity with doctor HTML list (doctor-only subset still applies).
    - ``in_revision``: only ``PUBLISHED`` documents with ``has_pending_revision``.
    """
    qs = (
        MedicalDocument.objects.select_related(
            "queue_entry",
            "queue_entry__patient",
            "queue_entry__daily_queue",
            "locked_by_user",
        )
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=MedicalDocumentVersion.objects.order_by(
                    "-version_no"
                ).prefetch_related(
                    Prefetch(
                        "outbox_events",
                        queryset=OutboxEvent.objects.order_by("-created_at"),
                    )
                ),
            )
        )
        .order_by("-updated_at")
    )
    if not _is_admin_or_manager_medical_oversight(user) and user is not None:
        qs = qs.filter(
            Q(created_by_user_id=user.id)
            | Q(queue_entry__daily_queue__assigned_doctor_id=user.id)
            | Q(status=MedicalDocStatus.DRAFT)
        )
    if status:
        qs = qs.filter(status=status)
    if queue_date is not None:
        qs = qs.filter(queue_entry__daily_queue__queue_date=queue_date)
    if patient_search and patient_search.strip():
        term = patient_search.strip()
        qs = qs.filter(
            Q(queue_entry__patient__last_name__icontains=term)
            | Q(queue_entry__patient__first_name__icontains=term)
        )
    if scope == "in_revision":
        qs = qs.filter(
            status=MedicalDocStatus.PUBLISHED,
            has_pending_revision=True,
        )
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    items = list(qs[start:end])
    return items, total


def list_doctor_work_queue(
    *,
    status: str | None = None,
    queue_date: date | None = None,
    patient_search: str | None = None,
    scope: str = "all",
    user: Any = None,
    page: int = 1,
    page_size: int = DEFAULT_LIST_LIMIT,
) -> tuple[list[dict[str, Any]], int]:
    """
    List doctor work queue: queue entries with submitted intake (ankieta pacjenta).
    """
    qs = PatientIntakeForm.objects.filter(
        form_status__in=(IntakeStatus.SUBMITTED, IntakeStatus.REOPENED)
    ).select_related("queue_entry", "queue_entry__patient", "queue_entry__daily_queue")
    if user is not None:
        personal = (
            Q(queue_entry__medical_document__created_by_user_id=user.id)
            | Q(queue_entry__daily_queue__assigned_doctor_id=user.id)
            | Q(queue_entry__medical_document__versions__published_by_user_id=user.id)
        )
        shared_draft_or_pending = Q(queue_entry__medical_document__isnull=True) | Q(
            queue_entry__medical_document__status=MedicalDocStatus.DRAFT
        )
        in_revision_q = Q(
            queue_entry__medical_document__status=MedicalDocStatus.PUBLISHED,
            queue_entry__medical_document__has_pending_revision=True,
        )
        if _is_admin_or_manager_medical_oversight(user):
            if scope == "mine":
                qs = qs.filter(personal)
            elif scope == "published_by_me":
                qs = qs.filter(
                    queue_entry__medical_document__versions__published_by_user_id=user.id
                )
            elif scope == "in_revision":
                qs = qs.filter(in_revision_q)
        else:
            if scope == "mine":
                qs = qs.filter(personal)
            elif scope == "published_by_me":
                qs = qs.filter(
                    queue_entry__medical_document__versions__published_by_user_id=user.id
                )
            elif scope == "in_revision":
                qs = qs.filter(in_revision_q & personal)
            else:
                qs = qs.filter(shared_draft_or_pending | personal)
    if status:
        qs = qs.filter(
            queue_entry_id__in=MedicalDocument.objects.filter(
                status=status
            ).values_list("queue_entry_id", flat=True)
        )
    if queue_date is not None:
        qs = qs.filter(queue_entry__daily_queue__queue_date=queue_date)
    if patient_search and patient_search.strip():
        term = patient_search.strip()
        qs = qs.filter(
            Q(queue_entry__patient__last_name__icontains=term)
            | Q(queue_entry__patient__first_name__icontains=term)
        )
    qs = qs.distinct().order_by(
        "-queue_entry__daily_queue__queue_date", "-submitted_at"
    )
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    intake_forms = list(qs[start:end])
    if not intake_forms:
        return [], total
    queue_entry_ids = [f.queue_entry_id for f in intake_forms]
    docs = (
        MedicalDocument.objects.filter(queue_entry_id__in=queue_entry_ids)
        .select_related("queue_entry", "locked_by_user")
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=MedicalDocumentVersion.objects.order_by(
                    "-version_no"
                ).prefetch_related(
                    Prefetch(
                        "outbox_events",
                        queryset=OutboxEvent.objects.order_by("-created_at"),
                    )
                ),
            )
        )
    )
    doc_by_entry: dict[uuid.UUID, MedicalDocument] = {d.queue_entry_id: d for d in docs}
    doc_ids = [d.id for d in docs]
    published_versions = (
        MedicalDocumentVersion.objects.filter(
            medical_document_id__in=doc_ids,
            version_status=DocVersionStatus.PUBLISHED,
        )
        .select_related("published_by_user")
        .order_by("medical_document_id", "-version_no")
    )
    published_by_display_by_doc_id: dict[uuid.UUID, str] = {}
    for ver in published_versions:
        if ver.medical_document_id in published_by_display_by_doc_id:
            continue
        published_by_display_by_doc_id[ver.medical_document_id] = (
            _staff_user_display_name(ver.published_by_user)
        )
    list_items = []
    for intake_form in intake_forms:
        entry = intake_form.queue_entry
        doc = doc_by_entry.get(entry.id)
        patient = entry.patient
        queue = entry.daily_queue
        versions = list(doc.versions.all())[:1] if doc else []
        latest = versions[0] if versions else None
        events_by_type = {}
        if latest:
            events_by_type = {e.event_type: e for e in latest.outbox_events.all()}
        hidrive_status = (
            outbox_event_stage_status(
                events_by_type.get(OutboxEventType.HIDRIVE_UPLOAD),
                completed=bool(latest and latest.hidrive_sent),
            )
            if latest
            else None
        )
        sms_status = (
            outbox_event_stage_status(
                events_by_type.get(OutboxEventType.SMS_SEND),
                completed=bool(latest and latest.sms_sent),
            )
            if latest
            else None
        )
        retryable_event = latest_retryable_outbox_event(latest) if latest else None
        locked_eff, locked_name, locked_at = (
            get_document_lock_state(doc) if doc else (False, None, None)
        )
        is_published = bool(doc and doc.status == MedicalDocStatus.PUBLISHED)
        is_locked_by_other = bool(
            doc
            and locked_eff
            and doc.locked_by_user_id != user.id
            and not _is_admin_or_manager_medical_oversight(user)
        )
        # Doctor list row tint: yellow = active edit lock (semaphore) on DRAFT
        row_has_edit_semaphore = bool(
            doc and doc.status == MedicalDocStatus.DRAFT and locked_eff
        )
        # Green row = published and outbound pipeline finished (PDF + HiDrive + SMS)
        row_is_fully_delivered = bool(
            doc
            and doc.status == MedicalDocStatus.PUBLISHED
            and latest
            and latest.pdf_generation_status == PdfStatus.COMPLETED
            and latest.hidrive_sent
            and latest.sms_sent
        )
        has_pending_revision = bool(doc and doc.has_pending_revision)
        published_version_no = doc.published_version_no if doc else None
        list_items.append(
            {
                "document_id": str(doc.id) if doc else None,
                "queue_entry_id": str(entry.id),
                "intake_form_id": str(intake_form.id),
                "patient": {
                    "id": str(patient.id),
                    "first_name": patient.first_name,
                    "last_name": patient.last_name,
                    "date_of_birth": patient.date_of_birth.isoformat(),
                },
                "queue_date": queue.queue_date.isoformat(),
                "status": doc.status if doc else "—",
                "published_by": (
                    published_by_display_by_doc_id.get(doc.id, "") if doc else ""
                ),
                "has_pending_revision": has_pending_revision,
                "published_version_no": published_version_no,
                "locked_by_username": locked_name,
                "locked_at": locked_at.isoformat() if locked_at else None,
                "is_locked_by_other": is_locked_by_other,
                "row_is_published": is_published,
                "row_has_edit_semaphore": row_has_edit_semaphore,
                "row_is_fully_delivered": row_is_fully_delivered,
                "pdf_generation_status": (
                    latest.pdf_generation_status if latest else None
                ),
                "hidrive_sent": latest.hidrive_sent if latest else False,
                "sms_sent": latest.sms_sent if latest else False,
                "hidrive_status": hidrive_status,
                "sms_status": sms_status,
                "processing_error_message": (
                    latest_version_processing_error_message(latest) if latest else None
                ),
                "can_retry_processing": retryable_event is not None,
                "retry_event_status": (
                    retryable_event.status if retryable_event else None
                ),
            }
        )
    return list_items, total


def get_medical_document_context(
    *,
    medical_document_id: uuid.UUID,
    form_locale: str = "de-DE",
    user: Any = None,
) -> dict[str, Any]:
    """
    Build full context for doctor view: document, intake summary, current (latest) version.
    When user is provided and has consulting_room_id set, raises ObjectDoesNotExist if document
    is from another cabinet. Raises ObjectDoesNotExist if document not found.
    """
    doc = (
        MedicalDocument.objects.select_related(
            "queue_entry",
            "queue_entry__patient",
            "queue_entry__daily_queue",
            "intake_form",
            "locked_by_user",
        )
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=MedicalDocumentVersion.objects.order_by(
                    "-version_no"
                ).prefetch_related(
                    Prefetch(
                        "outbox_events",
                        queryset=OutboxEvent.objects.order_by("-created_at"),
                    )
                ),
            )
        )
        .get(id=medical_document_id)
    )
    if user is not None:
        check_doctor_document_access(doc, user)
    latest_version = doc.versions.all()[:1]
    current_version = latest_version[0] if latest_version else None

    intake_summary: dict[str, Any]
    if doc.intake_form_id is None:
        patient = doc.queue_entry.patient
        intake_summary = {
            "consents": [],
            "body_map_data": [],
            "anamnesis_questions": [],
            "anamnesis_answers": [],
            "patient": {
                "id": str(patient.id),
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "date_of_birth": (
                    patient.date_of_birth.isoformat() if patient.date_of_birth else None
                ),
                "phone": patient.phone,
                "email": patient.email,
            },
        }
    else:
        intake_context = get_intake_form_context(
            intake_form_id=doc.intake_form_id,
            form_locale=form_locale,
            tablet_restrict_to_today=False,
        )
        anamnesis_questions_raw = intake_context.get("anamnesis_questions", [])
        anamnesis_questions: list[dict[str, Any]] = (
            anamnesis_questions_raw if isinstance(anamnesis_questions_raw, list) else []
        )
        intake_summary = {
            "consents": intake_context.get("consents", []),
            "body_map_data": intake_context.get("body_map_data", []),
            "anamnesis_questions": anamnesis_questions,
            "anamnesis_answers": [
                {
                    "question_code": q.get("question_code"),
                    "selected_option_codes": (q.get("answer") or {}).get(
                        "selected_option_codes"
                    )
                    or [],
                    "free_text": (q.get("answer") or {}).get("free_text"),
                }
                for q in anamnesis_questions
            ],
            "patient": intake_context.get("patient"),
        }

    current_version_payload: dict[str, Any] | None = None
    if current_version:
        events_by_type = {e.event_type: e for e in current_version.outbox_events.all()}
        retryable_event = latest_retryable_outbox_event(current_version)
        if current_version.local_pdf_deleted_at:
            current_version_payload = {
                "version_no": current_version.version_no,
                "version_status": current_version.version_status,
                "retention_expired": True,
                "local_pdf_deleted_at": current_version.local_pdf_deleted_at.isoformat(),
                "hidrive_path": current_version.hidrive_path,
                "pdf_checksum_sha256": current_version.pdf_checksum_sha256,
                "pdf_generation_status": current_version.pdf_generation_status,
                "hidrive_sent": current_version.hidrive_sent,
                "sms_sent": current_version.sms_sent,
                "hidrive_status": outbox_event_stage_status(
                    events_by_type.get(OutboxEventType.HIDRIVE_UPLOAD),
                    completed=current_version.hidrive_sent,
                ),
                "sms_status": outbox_event_stage_status(
                    events_by_type.get(OutboxEventType.SMS_SEND),
                    completed=current_version.sms_sent,
                ),
                "processing_error_message": latest_version_processing_error_message(
                    current_version
                ),
                "can_retry_processing": retryable_event is not None
                and (
                    getattr(user, "is_admin_role", False)
                    or getattr(user, "is_reception", False)
                    or getattr(user, "is_manager", False)
                ),
                "publish_locale": current_version.publish_locale,
                "published_at": (
                    current_version.published_at.isoformat()
                    if current_version.published_at
                    else None
                ),
            }
        else:
            current_version_payload = {
                "version_no": current_version.version_no,
                "version_status": current_version.version_status,
                "medical_payload_schema_version": current_version.medical_payload_schema_version,
                "medical_payload": current_version.medical_payload,
                "diagnosis_code": current_version.diagnosis_code,
                "procedure_code": current_version.procedure_code,
                "pdf_generation_status": current_version.pdf_generation_status,
                "hidrive_sent": current_version.hidrive_sent,
                "sms_sent": current_version.sms_sent,
                "hidrive_status": outbox_event_stage_status(
                    events_by_type.get(OutboxEventType.HIDRIVE_UPLOAD),
                    completed=current_version.hidrive_sent,
                ),
                "sms_status": outbox_event_stage_status(
                    events_by_type.get(OutboxEventType.SMS_SEND),
                    completed=current_version.sms_sent,
                ),
                "processing_error_message": latest_version_processing_error_message(
                    current_version
                ),
                "can_retry_processing": retryable_event is not None
                and (
                    getattr(user, "is_admin_role", False)
                    or getattr(user, "is_reception", False)
                    or getattr(user, "is_manager", False)
                ),
                "publish_locale": current_version.publish_locale,
                "published_at": (
                    current_version.published_at.isoformat()
                    if current_version.published_at
                    else None
                ),
            }

    lock_eff, lock_name, lock_at = get_document_lock_state(doc)
    return {
        "id": str(doc.id),
        "queue_entry_id": str(doc.queue_entry_id),
        "intake_form_id": str(doc.intake_form_id) if doc.intake_form_id else None,
        "status": doc.status,
        "current_version_no": doc.current_version_no,
        "published_version_no": doc.published_version_no,
        "has_pending_revision": doc.has_pending_revision,
        "last_published_at": (
            doc.last_published_at.isoformat() if doc.last_published_at else None
        ),
        "locked_by_user_id": (
            str(doc.locked_by_user_id) if doc.locked_by_user_id else None
        ),
        "locked_by_username": lock_name if lock_eff else None,
        "locked_at": lock_at.isoformat() if lock_at and lock_eff else None,
        "intake_summary": intake_summary,
        "current_version": current_version_payload,
    }


@transaction.atomic
def retry_latest_document_processing(
    *,
    medical_document_id: uuid.UUID,
    actor: StaffUser,
    reason: str,
) -> OutboxEvent:
    if not (
        actor.is_admin_role or actor.is_reception or getattr(actor, "is_manager", False)
    ):
        raise DomainError(
            domain_message("other.domain.document_processing_retry_role"),
            api_message_key="other.domain.document_processing_retry_role",
        )
    doc = (
        MedicalDocument.objects.select_for_update()
        .select_related("queue_entry__daily_queue")
        .get(id=medical_document_id)
    )
    latest_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(medical_document_id=medical_document_id)
        .order_by("-version_no")
        .prefetch_related(
            Prefetch(
                "outbox_events", queryset=OutboxEvent.objects.order_by("-created_at")
            )
        )
        .first()
    )
    if latest_version is None:
        raise DomainError(
            domain_message("other.domain.medical_document_no_version"),
            api_message_key="other.domain.medical_document_no_version",
        )
    retryable = latest_retryable_outbox_event(latest_version)
    if retryable is None:
        raise DomainError(
            domain_message("other.domain.no_retryable_processing_step"),
            api_message_key="other.domain.no_retryable_processing_step",
        )
    retried = retry_outbox_event(event=retryable, reason=reason, actor_user_id=actor.id)
    create_audit_event(
        event_type="DOCUMENT_PROCESSING_RETRY_REQUESTED",
        actor_user_id=actor.id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        outbox_event_id=retried.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "medical_document_version_id": str(latest_version.id),
            "event_type": retried.event_type,
            "reason": reason,
            **assigned_doctor_audit_metadata(doc),
        },
    )
    return retried
