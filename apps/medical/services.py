from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.utils import timezone

from apps.core.api_utils import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    safe_parse_positive_int,
)
from apps.core.domain_messages import domain_message
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
    MedicalDocumentVersion,
    PdfStatus,
)
from apps.operations.services import create_audit_event
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.services import retry_outbox_event, _try_delete_file
from apps.reception.models import QueueEntry
from apps.users.models import StaffUser

DOCUMENT_LOCK_TIMEOUT_HOURS = 24


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
    """Create medical document for queue entry if not existing. Intake must be SUBMITTED."""
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


@transaction.atomic
def save_draft_document_version(
    *,
    medical_document_id: uuid.UUID,
    updated_by_user_id: uuid.UUID,
    medical_payload_schema_version: int = 1,
    medical_payload: dict,
    diagnosis_code: str | None = None,
    procedure_code: str | None = None,
) -> MedicalDocumentVersion:
    """
    Save draft payload for a medical document.

    If latest version is DRAFT it is updated in place; otherwise a new draft
    version is created with incremented `version_no`.
    """
    medical_document = MedicalDocument.objects.select_for_update().get(
        id=medical_document_id
    )

    latest_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(medical_document_id=medical_document_id)
        .order_by("-version_no")
        .first()
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
    medical_document.current_version_no = created_version.version_no
    medical_document.status = MedicalDocStatus.DRAFT
    medical_document.updated_by_user_id = updated_by_user_id
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
            **assigned_doctor_audit_metadata(medical_document),
        },
    )
    return created_version


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
    if in_progress_version:
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

    medical_document.status = MedicalDocStatus.PUBLISHED
    medical_document.current_version_no = draft_version.version_no
    medical_document.last_published_at = requested_at
    medical_document.updated_by_user_id = published_by_user_id
    medical_document.locked_by_user_id = None
    medical_document.locked_at = None
    medical_document.save(
        update_fields=[
            "status",
            "current_version_no",
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
    if scope not in {"all", "mine", "published_by_me"}:
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
    ``scope`` is accepted for API/doctor-list param parity; the API currently keeps
    the historical "all visible" behavior and does not branch on it here.
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
        form_status=IntakeStatus.SUBMITTED
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
        if _is_admin_or_manager_medical_oversight(user):
            if scope == "mine":
                qs = qs.filter(personal)
            elif scope == "published_by_me":
                qs = qs.filter(
                    queue_entry__medical_document__versions__published_by_user_id=user.id
                )
        else:
            if scope == "mine":
                qs = qs.filter(personal)
            elif scope == "published_by_me":
                qs = qs.filter(
                    queue_entry__medical_document__versions__published_by_user_id=user.id
                )
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

    intake_context = get_intake_form_context(
        intake_form_id=doc.intake_form_id,
        form_locale=form_locale,
        tablet_restrict_to_today=False,
    )
    anamnesis_questions = intake_context.get("anamnesis_questions", [])
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
        "intake_form_id": str(doc.intake_form_id),
        "status": doc.status,
        "current_version_no": doc.current_version_no,
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
