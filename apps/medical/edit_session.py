"""Doctor Befund edit-session domain logic (holder + single write token)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.medical.constants import (
    DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS,
    DOCUMENT_LOCK_TIMEOUT_HOURS,
)
from apps.medical.models import (
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
)
from apps.operations.services import create_audit_event
from apps.users.display import staff_user_display_name
from apps.users.models import StaffUser

EditSessionMode = Literal["acquired", "resumed", "reclaimed"]


def is_doctor_befund_source_type(doc: MedicalDocument) -> bool:
    return doc.source_type in (
        MedicalDocumentSourceType.DIGITAL_INTAKE,
        MedicalDocumentSourceType.PAPER_INTAKE,
    )


def doctor_befund_edit_lock_applies(doc: MedicalDocument) -> bool:
    """Whether the doctor Befund edit semaphore applies (not EXTERNAL_UPLOAD)."""
    if not is_doctor_befund_source_type(doc):
        return False
    if doc.status == MedicalDocStatus.DRAFT:
        return True
    return doc.status == MedicalDocStatus.PUBLISHED and bool(doc.has_pending_revision)


@dataclass(frozen=True, slots=True)
class DoctorEditSessionResult:
    mode: EditSessionMode
    edit_session_token: uuid.UUID
    edit_session_revision: int
    draft_revision: int


@dataclass(frozen=True, slots=True)
class DoctorActiveLockSummary:
    medical_document_id: uuid.UUID
    patient_display: str
    status: str
    has_pending_revision: bool


class EditSessionResponseError(Exception):
    """Maps to a stable API ``error_key`` and HTTP status."""

    __slots__ = ("error_key", "http_status", "payload")

    def __init__(
        self,
        *,
        error_key: str,
        http_status: int,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_key)
        self.error_key = error_key
        self.http_status = http_status
        self.payload = payload or {}
        if http_status in (409, 423):
            try:
                from apps.operations.prom_metrics import record_befund_edit_conflict

                record_befund_edit_conflict(reason=error_key)
            except Exception:
                pass


def _assert_doctor_actor(user: Any) -> StaffUser:
    if not getattr(user, "is_doctor", False):
        raise DomainError(
            domain_message("other.domain.medical_document_edit_doctor_role_required"),
            api_message_key="other.domain.medical_document_edit_doctor_role_required",
        )
    return user


def _lock_cutoff(*, now: datetime) -> datetime:
    return now - timedelta(hours=DOCUMENT_LOCK_TIMEOUT_HOURS)


def _doctor_active_lock_filter(*, cutoff: datetime) -> Q:
    return Q(
        locked_by_user_id__isnull=False,
        locked_at__gte=cutoff,
        source_type__in=(
            MedicalDocumentSourceType.DIGITAL_INTAKE,
            MedicalDocumentSourceType.PAPER_INTAKE,
        ),
    ) & (
        Q(status=MedicalDocStatus.DRAFT)
        | Q(status=MedicalDocStatus.PUBLISHED, has_pending_revision=True)
    )


def count_doctor_active_document_locks(
    *,
    user_id: uuid.UUID,
    now: datetime | None = None,
    exclude_medical_document_id: uuid.UUID | None = None,
) -> int:
    at = now or timezone.now()
    qs = MedicalDocument.objects.filter(
        _doctor_active_lock_filter(cutoff=_lock_cutoff(now=at)),
        locked_by_user_id=user_id,
    )
    if exclude_medical_document_id is not None:
        qs = qs.exclude(id=exclude_medical_document_id)
    return qs.count()


def list_doctor_active_lock_summaries(
    *,
    user: StaffUser,
    now: datetime | None = None,
) -> list[DoctorActiveLockSummary]:
    at = now or timezone.now()
    docs = (
        MedicalDocument.objects.filter(
            _doctor_active_lock_filter(cutoff=_lock_cutoff(now=at)),
            locked_by_user_id=user.id,
        )
        .select_related("queue_entry__patient")
        .order_by("-locked_at")[:DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS]
    )
    summaries: list[DoctorActiveLockSummary] = []
    for doc in docs:
        patient = doc.queue_entry.patient
        summaries.append(
            DoctorActiveLockSummary(
                medical_document_id=doc.id,
                patient_display=f"{patient.last_name}, {patient.first_name}",
                status=doc.status,
                has_pending_revision=bool(doc.has_pending_revision),
            )
        )
    return summaries


def _effective_lock_holder_id(
    doc: MedicalDocument, *, now: datetime
) -> uuid.UUID | None:
    if not doc.locked_by_user_id or not doc.locked_at:
        return None
    if doc.locked_at < _lock_cutoff(now=now):
        return None
    return doc.locked_by_user_id


def _clear_edit_session_lock_fields(doc: MedicalDocument) -> None:
    doc.locked_by_user_id = None
    doc.locked_at = None
    doc.edit_session_token = None
    doc.last_edit_session_request_id = None
    doc.last_previewed_draft_revision = None
    doc.last_draft_request_id = None
    doc.last_draft_request_base_revision = None
    doc.last_draft_request_result_revision = None


def _session_lock_update_fields(*, include_holder: bool = True) -> list[str]:
    fields = [
        "locked_at",
        "edit_session_token",
        "edit_session_revision",
        "last_edit_session_request_id",
        "last_previewed_draft_revision",
        "updated_at",
    ]
    if include_holder:
        fields = ["locked_by_user_id", *fields]
    return fields


def _audit_edit_session_event(
    *,
    event_type: str,
    doc: MedicalDocument,
    actor_user_id: uuid.UUID,
    metadata: dict[str, Any],
) -> None:
    create_audit_event(
        event_type=event_type,
        actor_user_id=actor_user_id,
        patient_id=doc.queue_entry.patient_id,
        medical_document_id=doc.id,
        context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
        metadata=metadata,
    )


@transaction.atomic
def start_doctor_edit_session(
    *,
    medical_document_id: uuid.UUID,
    user: Any,
    purpose: Literal["edit", "amend"] = "edit",
    edit_session_token: uuid.UUID | None = None,
    edit_session_request_id: uuid.UUID | None = None,
    expected_edit_session_revision: int | None = None,
    reclaim_confirmed: bool = False,
) -> DoctorEditSessionResult:
    """Acquire, resume, or reclaim a doctor Befund edit session."""
    doctor = _assert_doctor_actor(user)
    now = timezone.now()

    doc = (
        MedicalDocument.objects.select_for_update()
        .select_related("queue_entry__daily_queue", "queue_entry__patient")
        .get(id=medical_document_id)
    )

    if not is_doctor_befund_source_type(doc):
        raise DomainError(
            domain_message("other.domain.edit_session_not_applicable"),
            api_message_key="other.domain.edit_session_not_applicable",
        )

    if purpose == "amend":
        if doc.status != MedicalDocStatus.PUBLISHED or doc.has_pending_revision:
            raise DomainError(
                domain_message("other.domain.edit_session_document_read_only"),
                api_message_key="other.domain.edit_session_document_read_only",
            )
        from apps.medical.services import (
            begin_pending_revision_from_published,
            user_may_start_amend_revision,
        )

        if not user_may_start_amend_revision(doc, doctor.id):
            raise DomainError(
                domain_message("other.domain.amend_publisher_only"),
                api_message_key="other.domain.amend_publisher_only",
            )
    elif not doctor_befund_edit_lock_applies(doc):
        raise DomainError(
            domain_message("other.domain.edit_session_document_read_only"),
            api_message_key="other.domain.edit_session_document_read_only",
        )

    holder_id = _effective_lock_holder_id(doc, now=now)
    had_expired_lock = (
        doc.locked_by_user_id is not None
        and doc.locked_at is not None
        and holder_id is None
    )

    if holder_id is not None and holder_id != doctor.id:
        holder = StaffUser.objects.filter(id=holder_id).first()
        raise EditSessionResponseError(
            error_key="document_locked_by_other",
            http_status=423,
            payload={"locked_by_username": staff_user_display_name(holder)},
        )

    if purpose == "amend":
        begin_pending_revision_from_published(
            medical_document=doc,
            actor_user_id=doctor.id,
        )
        doc.refresh_from_db()

    if holder_id == doctor.id:
        if (
            edit_session_token is not None
            and doc.edit_session_token == edit_session_token
        ):
            doc.locked_at = now
            doc.save(update_fields=["locked_at", "updated_at"])
            _audit_edit_session_event(
                event_type="DOCUMENT_LOCK_RESUMED",
                doc=doc,
                actor_user_id=doctor.id,
                metadata={
                    "mode": "resumed",
                    "draft_revision": doc.draft_revision,
                    "edit_session_revision": doc.edit_session_revision,
                },
            )
            assert doc.edit_session_token is not None
            return DoctorEditSessionResult(
                mode="resumed",
                edit_session_token=doc.edit_session_token,
                edit_session_revision=doc.edit_session_revision,
                draft_revision=doc.draft_revision,
            )

        if edit_session_request_id is not None and (
            doc.last_edit_session_request_id == edit_session_request_id
        ):
            assert doc.edit_session_token is not None
            return DoctorEditSessionResult(
                mode="reclaimed",
                edit_session_token=doc.edit_session_token,
                edit_session_revision=doc.edit_session_revision,
                draft_revision=doc.draft_revision,
            )

        if reclaim_confirmed:
            if expected_edit_session_revision != doc.edit_session_revision:
                raise EditSessionResponseError(
                    error_key="reclaim_superseded",
                    http_status=409,
                    payload={
                        "edit_session_revision": doc.edit_session_revision,
                    },
                )
            return _reclaim_edit_session(
                doc=doc,
                doctor=doctor,
                now=now,
                edit_session_request_id=edit_session_request_id,
            )

        raise EditSessionResponseError(
            error_key="edit_session_reclaim_confirmation_required",
            http_status=409,
            payload={"edit_session_revision": doc.edit_session_revision},
        )

    if count_doctor_active_document_locks(user_id=doctor.id, now=now) >= (
        DOCTOR_MAX_ACTIVE_DOCUMENT_LOCKS
    ):
        locked_docs = list_doctor_active_lock_summaries(user=doctor, now=now)
        raise EditSessionResponseError(
            error_key="doctor_lock_limit_reached",
            http_status=409,
            payload={
                "locked_documents": [
                    {
                        "medical_document_id": str(item.medical_document_id),
                        "patient_display": item.patient_display,
                        "status": item.status,
                        "has_pending_revision": item.has_pending_revision,
                    }
                    for item in locked_docs
                ],
            },
        )

    StaffUser.objects.select_for_update().filter(id=doctor.id).exists()

    new_token = uuid.uuid4()
    doc.locked_by_user_id = doctor.id
    doc.locked_at = now
    doc.edit_session_token = new_token
    doc.edit_session_revision += 1
    doc.last_edit_session_request_id = edit_session_request_id
    doc.last_previewed_draft_revision = None
    doc.save(update_fields=_session_lock_update_fields())

    event_type = (
        "DOCUMENT_LOCK_EXPIRED_REPLACED"
        if had_expired_lock
        else "DOCUMENT_LOCK_ACQUIRED"
    )
    _audit_edit_session_event(
        event_type=event_type,
        doc=doc,
        actor_user_id=doctor.id,
        metadata={
            "mode": "acquired",
            "draft_revision": doc.draft_revision,
            "edit_session_revision": doc.edit_session_revision,
        },
    )
    return DoctorEditSessionResult(
        mode="acquired",
        edit_session_token=new_token,
        edit_session_revision=doc.edit_session_revision,
        draft_revision=doc.draft_revision,
    )


def _reclaim_edit_session(
    *,
    doc: MedicalDocument,
    doctor: StaffUser,
    now: datetime,
    edit_session_request_id: uuid.UUID | None,
) -> DoctorEditSessionResult:
    new_token = uuid.uuid4()
    previous_token = doc.edit_session_token
    doc.locked_at = now
    doc.edit_session_token = new_token
    doc.edit_session_revision += 1
    doc.last_edit_session_request_id = edit_session_request_id
    doc.last_previewed_draft_revision = None
    doc.save(update_fields=_session_lock_update_fields(include_holder=False))

    previous_prefix = str(previous_token)[:8] if previous_token is not None else None
    _audit_edit_session_event(
        event_type="DOCUMENT_LOCK_RECLAIMED",
        doc=doc,
        actor_user_id=doctor.id,
        metadata={
            "mode": "reclaimed",
            "draft_revision": doc.draft_revision,
            "edit_session_revision": doc.edit_session_revision,
            "previous_token_prefix": previous_prefix,
        },
    )
    return DoctorEditSessionResult(
        mode="reclaimed",
        edit_session_token=new_token,
        edit_session_revision=doc.edit_session_revision,
        draft_revision=doc.draft_revision,
    )


def document_locked_by_other_for_user(
    doc: MedicalDocument,
    *,
    user: Any,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    """True when another doctor holds an effective edit lock on a Befund document."""
    if not doctor_befund_edit_lock_applies(doc):
        return False, None
    at = now or timezone.now()
    holder_id = _effective_lock_holder_id(doc, now=at)
    if holder_id is None or holder_id == getattr(user, "id", None):
        return False, None
    holder = StaffUser.objects.filter(id=holder_id).first()
    return True, staff_user_display_name(holder)


@transaction.atomic
def release_doctor_edit_session_lock(
    *, medical_document_id: uuid.UUID, user: Any
) -> bool:
    """Clear holder lock and session markers; doctor holder only."""
    if not getattr(user, "is_doctor", False):
        return False
    doc = MedicalDocument.objects.select_for_update().get(id=medical_document_id)
    if not doc.locked_by_user_id:
        return True
    if doc.locked_by_user_id != user.id:
        return False
    _clear_edit_session_lock_fields(doc)
    doc.save(
        update_fields=[
            "locked_by_user_id",
            "locked_at",
            "edit_session_token",
            "last_edit_session_request_id",
            "last_previewed_draft_revision",
            "last_draft_request_id",
            "last_draft_request_base_revision",
            "last_draft_request_result_revision",
            "updated_at",
        ]
    )
    return True
