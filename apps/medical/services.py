from __future__ import annotations

import re
import tempfile
import unicodedata
import uuid
from os import close as os_close
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction
from django.db.models import (
    Case,
    Exists,
    F,
    IntegerField,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Value,
    When,
)
from django.utils import timezone

from apps.core.api_utils import safe_parse_positive_int
from apps.core.constants import DEFAULT_LIST_LIMIT
from apps.core.list_pagination import parse_page_size
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
from apps.medical.constants import (
    DOCTOR_LIST_UNPUBLISHED_SLA_HOURS,
    DOCUMENT_LOCK_TIMEOUT_HOURS,
    EXTERNAL_UPLOAD_MAX_BYTES,
    PAPER_INTAKE_AUTH_REASON_MAX_LEN,
    PAPER_INTAKE_AUTH_REASON_MIN_LEN,
    PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT,
)
from apps.medical.external_pdf_service import (
    hidrive_incoming_dir,
    hidrive_processed_dir,
)
from apps.integrations.hidrive.auth import HiDriveAuthError
from apps.integrations.hidrive.client import HiDriveApiError, get_hidrive_adapter
from apps.medical.models import (
    DocVersionStatus,
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocStatus,
    MedicalDocument,
    MedicalDocumentSourceType,
    MedicalDocumentVersion,
    PaperIntakeAuthorization,
    PdfStatus,
)
from apps.medical.edit_session import (
    EditSessionResponseError,
    clear_edit_session_lock_fields,
    doctor_befund_edit_lock_applies,
    effective_lock_holder_id,
    release_doctor_edit_session_lock,
    start_doctor_edit_session,
)
from apps.operations.services import create_audit_event
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.services import retry_outbox_event, _try_delete_file
from apps.reception.models import QueueEntry, QueueEntryStatus
from apps.users.display import staff_user_display_name
from apps.users.models import StaffUser
from pypdf import PdfReader

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


def _paper_intake_authorization_context_for_document(
    doc: MedicalDocument,
) -> dict[str, Any] | None:
    """Snapshot from ``MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE`` audit (authorization row is deleted at create)."""
    if doc.source_type != MedicalDocumentSourceType.PAPER_INTAKE:
        return None
    from apps.operations.models import AuditEvent

    ev = (
        AuditEvent.objects.filter(
            medical_document_id=doc.id,
            event_type="MEDICAL_DOCUMENT_CREATED_WITHOUT_INTAKE",
        )
        .order_by("-event_time")
        .first()
    )
    if ev is None or not isinstance(ev.metadata, dict):
        return None
    meta = ev.metadata
    raw_by = meta.get("paper_intake_authorized_by_id")
    by_uuid: uuid.UUID | None = None
    if raw_by:
        try:
            by_uuid = uuid.UUID(str(raw_by))
        except (ValueError, TypeError):
            by_uuid = None
    display = ""
    if by_uuid is not None:
        try:
            authorizer = StaffUser.objects.only(
                "username", "first_name", "last_name"
            ).get(id=by_uuid)
            display = staff_user_display_name(authorizer) or (authorizer.username or "")
        except StaffUser.DoesNotExist:
            display = str(by_uuid)

    reason = meta.get("paper_intake_authorization_reason_snapshot")
    authorized_at = meta.get("paper_intake_authorized_at")

    return {
        "authorized_by_user_id": str(by_uuid) if by_uuid else None,
        "authorized_by_username": display or None,
        "authorized_at": authorized_at if isinstance(authorized_at, str) else None,
        "reason": reason if isinstance(reason, str) else None,
    }


def _is_admin_or_manager_medical_oversight(user: Any) -> bool:
    """Pełen widok kolejki / dokumentów jak admin (rola Manager = nadzór operacyjny)."""
    return bool(
        getattr(user, "is_admin_role", False) or getattr(user, "is_manager", False)
    )


@dataclass(frozen=True, slots=True)
class DoctorAccessAuditContext:
    """Optional HTTP context for access-denied audit (client still receives 404)."""

    client_ip: str | None = None


def _doctor_queue_unpublished_q() -> Q:
    """Tier 0 work queue: no document, first draft, or open revision."""
    return (
        Q(medical_document__isnull=True)
        | Q(medical_document__status=MedicalDocStatus.DRAFT)
        | Q(
            medical_document__status=MedicalDocStatus.PUBLISHED,
            medical_document__has_pending_revision=True,
        )
    )


def _queue_entry_published_by_user_at_record_version_q(*, user_id: uuid.UUID) -> Q:
    """Queue row visible: user published the version at ``published_version_no``."""
    return Q(
        Exists(
            MedicalDocumentVersion.objects.filter(
                medical_document__queue_entry_id=OuterRef("pk"),
                version_status=DocVersionStatus.PUBLISHED,
                published_by_user_id=user_id,
                version_no=OuterRef("medical_document__published_version_no"),
            )
        )
    )


def _doctor_work_queue_visibility_q(*, user: Any) -> Q:
    """Doctor list/detail visibility: shared work (tier 0) or own published result (tier 1)."""
    return (
        _doctor_queue_unpublished_q()
        | _queue_entry_published_by_user_at_record_version_q(user_id=user.id)
    )


def _document_is_doctor_shared_work(doc: MedicalDocument) -> bool:
    if doc.status == MedicalDocStatus.DRAFT:
        return True
    return bool(doc.status == MedicalDocStatus.PUBLISHED and doc.has_pending_revision)


def user_may_start_amend_revision(doc: MedicalDocument, user_id: uuid.UUID) -> bool:
    """Whether a doctor may start a pending revision on clean PUBLISHED."""
    return _user_is_publisher_of_record_version(doc, user_id)


def _user_is_publisher_of_record_version(
    doc: MedicalDocument, user_id: uuid.UUID
) -> bool:
    qs = MedicalDocumentVersion.objects.filter(
        medical_document_id=doc.id,
        version_status=DocVersionStatus.PUBLISHED,
        published_by_user_id=user_id,
    )
    if doc.published_version_no is not None:
        return qs.filter(version_no=doc.published_version_no).exists()
    return qs.exists()


def _doctor_may_access_medical_document(doc: MedicalDocument, user: Any) -> bool:
    if _is_admin_or_manager_medical_oversight(user):
        return True
    if not getattr(user, "is_doctor", False):
        return False
    if _document_is_doctor_shared_work(doc):
        return True
    if (
        doc.status == MedicalDocStatus.PUBLISHED
        and not doc.has_pending_revision
        and _user_is_publisher_of_record_version(doc, user.id)
    ):
        return True
    return False


def _audit_medical_document_access_denied(
    *,
    document: MedicalDocument,
    user: Any,
    denial_reason: str,
    audit_context: DoctorAccessAuditContext | None,
) -> None:
    if audit_context is None:
        return
    queue = document.queue_entry
    daily = queue.daily_queue
    create_audit_event(
        event_type="MEDICAL_DOCUMENT_ACCESS_DENIED",
        actor_user_id=user.id,
        patient_id=queue.patient_id,
        medical_document_id=document.id,
        context_clinic_site_id=daily.clinic_site_id,
        metadata={
            "denial_reason": denial_reason,
            "client_ip": audit_context.client_ip,
        },
    )


def _audit_queue_entry_access_denied(
    *,
    queue_entry: QueueEntry,
    user: Any,
    denial_reason: str,
    audit_context: DoctorAccessAuditContext | None,
) -> None:
    if audit_context is None:
        return
    create_audit_event(
        event_type="QUEUE_ENTRY_ACCESS_DENIED",
        actor_user_id=user.id,
        patient_id=queue_entry.patient_id,
        context_clinic_site_id=queue_entry.daily_queue.clinic_site_id,
        metadata={
            "denial_reason": denial_reason,
            "queue_entry_id": str(queue_entry.id),
            "client_ip": audit_context.client_ip if audit_context else None,
        },
    )


def _assert_staff_user_may_publish_medical_document(*, actor: StaffUser) -> None:
    if not actor.is_doctor:
        raise DomainError(
            domain_message(
                "other.domain.medical_document_publish_doctor_role_required"
            ),
            api_message_key="other.domain.medical_document_publish_doctor_role_required",
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
    return True, staff_user_display_name(holder), doc.locked_at


@transaction.atomic
def acquire_document_lock(
    *, medical_document_id: uuid.UUID, user: Any
) -> tuple[bool, str | None]:
    """
    Legacy acquire wrapper around :func:`start_doctor_edit_session`.

    Doctor-only; auto-confirms reclaim when the caller already holds the document.
    """
    if not getattr(user, "is_doctor", False):
        return False, None
    doc = MedicalDocument.objects.get(id=medical_document_id)
    if not doctor_befund_edit_lock_applies(doc):
        return True, None

    base_kwargs = {
        "medical_document_id": medical_document_id,
        "user": user,
        "purpose": "edit",
    }
    try:
        start_doctor_edit_session(**base_kwargs)
        return True, None
    except EditSessionResponseError as exc:
        if exc.error_key == "document_locked_by_other":
            return False, exc.payload.get("locked_by_username")
        if exc.error_key == "edit_session_reclaim_confirmation_required":
            try:
                start_doctor_edit_session(
                    **base_kwargs,
                    reclaim_confirmed=True,
                    expected_edit_session_revision=int(
                        exc.payload["edit_session_revision"]
                    ),
                )
                return True, None
            except EditSessionResponseError as retry_exc:
                if retry_exc.error_key == "document_locked_by_other":
                    return False, retry_exc.payload.get("locked_by_username")
                raise
        if exc.error_key == "doctor_lock_limit_reached":
            return False, None
        raise


@transaction.atomic
def release_document_lock(*, medical_document_id: uuid.UUID, user: Any) -> bool:
    """Clear edit lock for the doctor holder only."""
    return release_doctor_edit_session_lock(
        medical_document_id=medical_document_id, user=user
    )


@transaction.atomic
def refresh_document_lock(*, medical_document_id: uuid.UUID, user: Any) -> bool:
    """
    Refresh ``locked_at`` for the current doctor holder.
    Returns False if another doctor holds an effective lock.

    A free/expired lock goes through ``start_doctor_edit_session`` (StaffUser
    then document). Refreshing an own lock takes only ``MedicalDocument`` and
    never ``StaffUser`` afterwards.
    """
    if not getattr(user, "is_doctor", False):
        return False
    doc = MedicalDocument.objects.get(id=medical_document_id)
    if not doctor_befund_edit_lock_applies(doc):
        return True

    now = timezone.now()
    holder_id = effective_lock_holder_id(doc, now=now)
    if holder_id is None:
        try:
            start_doctor_edit_session(
                medical_document_id=medical_document_id,
                user=user,
                purpose="edit",
            )
            return True
        except EditSessionResponseError:
            return False
    if holder_id != user.id:
        return False

    locked = MedicalDocument.objects.select_for_update().get(id=medical_document_id)
    if not doctor_befund_edit_lock_applies(locked):
        return True
    current_holder = effective_lock_holder_id(locked, now=timezone.now())
    if current_holder != user.id:
        return False
    locked.locked_at = timezone.now()
    locked.save(update_fields=["locked_at", "updated_at"])
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


def pdf_generation_stage_complete(
    version: MedicalDocumentVersion | None,
    events_by_type: dict[str, OutboxEvent],
) -> bool:
    """True when PDF stage matches list UI: ``PdfStatus.COMPLETED`` or outbox GENERATE_PDF PROCESSED."""
    if not version:
        return False
    if version.pdf_generation_status == PdfStatus.COMPLETED:
        return True
    ev = events_by_type.get("GENERATE_PDF")
    return bool(ev and ev.status == OutboxStatus.PROCESSED)


def work_queue_row_outbound_complete(
    *,
    version: MedicalDocumentVersion | None,
    events_by_type: dict[str, OutboxEvent],
) -> bool:
    """
    Whether outbound pipeline is fully complete for the doctor list row tint.

    Uses the same completion rules as column badges (``outbox_event_stage_status`` for
    HiDrive/SMS so PROCESSED events count even if denormalized flags lag). PDF treats
    ``PdfStatus.COMPLETED`` or GENERATE_PDF PROCESSED as complete.
    """
    if not version:
        return False
    if not pdf_generation_stage_complete(version, events_by_type):
        return False
    hidrive_ok = (
        outbox_event_stage_status(
            events_by_type.get("HIDRIVE_UPLOAD"),
            completed=bool(version.hidrive_sent),
        )
        == "COMPLETED"
    )
    sms_ok = (
        outbox_event_stage_status(
            events_by_type.get("SMS_SEND"),
            completed=bool(version.sms_sent),
        )
        == "COMPLETED"
    )
    return hidrive_ok and sms_ok


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
    for event_type in (
        "SMS_SEND",
        "HIDRIVE_UPLOAD",
        "GENERATE_PDF",
    ):
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


def check_doctor_document_access(
    document: MedicalDocument,
    user: Any,
    *,
    audit_context: DoctorAccessAuditContext | None = None,
) -> None:
    """
    Raise ObjectDoesNotExist if user does not have access (404 to the client).

    Doctors: shared work (DRAFT / open revision) or published result they published.
    Admin/Manager: full oversight.
    """
    if _doctor_may_access_medical_document(document, user):
        return
    denial_reason = "foreign_published"
    if (
        document.status == MedicalDocStatus.PUBLISHED
        and not document.has_pending_revision
    ):
        denial_reason = "not_publisher"
    elif not getattr(user, "is_doctor", False):
        denial_reason = "not_doctor"
    _audit_medical_document_access_denied(
        document=document,
        user=user,
        denial_reason=denial_reason,
        audit_context=audit_context,
    )
    raise ObjectDoesNotExist("Medical document not found.")


def check_doctor_queue_entry_access(
    queue_entry: QueueEntry,
    user: Any,
    *,
    audit_context: DoctorAccessAuditContext | None = None,
) -> None:
    """
    Raise ObjectDoesNotExist if user does not have access to the queue entry.

    Without a medical document, any doctor may open the entry (paper / intake queue).
    With a document, same rules as ``check_doctor_document_access``.

    Cancelled entries (``entry_status=CANCELLED``) are never openable via this path.
    """
    if queue_entry.entry_status == QueueEntryStatus.CANCELLED:
        _audit_queue_entry_access_denied(
            queue_entry=queue_entry,
            user=user,
            denial_reason="queue_entry_cancelled",
            audit_context=audit_context,
        )
        raise ObjectDoesNotExist("Queue entry not found.")
    if _is_admin_or_manager_medical_oversight(user):
        return
    md = MedicalDocument.objects.filter(queue_entry_id=queue_entry.id).first()
    if md is not None:
        check_doctor_document_access(md, user, audit_context=audit_context)
        return
    if getattr(user, "is_doctor", False):
        return
    _audit_queue_entry_access_denied(
        queue_entry=queue_entry,
        user=user,
        denial_reason="queue_not_visible",
        audit_context=audit_context,
    )
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
    queue_entry = QueueEntry.objects.get(id=queue_entry_id)
    if queue_entry.entry_status == QueueEntryStatus.CANCELLED:
        raise ObjectDoesNotExist("Queue entry not found.")
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


def _bootstrap_external_upload_draft_v1(
    medical_document: MedicalDocument,
    *,
    created_by_user_id: uuid.UUID,
) -> None:
    """Create DRAFT version 1 (empty payload) and align document status / version counter."""
    draft = MedicalDocumentVersion.objects.create(
        medical_document_id=medical_document.id,
        version_no=1,
        version_status=DocVersionStatus.DRAFT,
        medical_payload_schema_version=1,
        medical_payload={},
    )
    medical_document.current_version_no = draft.version_no
    medical_document.status = MedicalDocStatus.DRAFT
    medical_document.updated_by_user_id = created_by_user_id
    medical_document.save(
        update_fields=[
            "current_version_no",
            "status",
            "updated_by_user",
            "updated_at",
        ]
    )


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_external_upload_filename(original_name: str) -> str:
    """Return safe ASCII filename for HiDrive path under /external-upload."""
    raw_name = (original_name or "").strip().replace("\\", "/").split("/")[-1]
    raw_name = raw_name.replace("\x00", "")
    normalized = (
        unicodedata.normalize("NFKD", raw_name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    collapsed = _SAFE_FILENAME_RE.sub("_", normalized).strip("._-")
    if not collapsed:
        collapsed = f"external_{uuid.uuid4().hex[:12]}.pdf"
    if "." not in collapsed:
        collapsed = f"{collapsed}.pdf"
    return collapsed[:200]


def _assert_staff_user_may_act_on_external_upload(*, actor: StaffUser) -> None:
    """Reception, Admin, or Manager only — shared by external-upload document / upload / draft bind."""
    if not (actor.is_reception or actor.is_admin_role or actor.is_manager):
        raise DomainError(
            domain_message("other.domain.external_upload_staff_role_required"),
            api_message_key="other.domain.external_upload_staff_role_required",
        )


def _raise_external_upload_file_too_large() -> None:
    raise DomainError(
        domain_message("other.domain.external_upload_file_too_large").format(
            max_bytes=EXTERNAL_UPLOAD_MAX_BYTES
        ),
        api_message_key="other.domain.external_upload_file_too_large",
    )


def _assert_uploaded_file_within_byte_limit(uploaded_file: UploadedFile) -> None:
    """Reject uploads whose streamed body exceeds ``EXTERNAL_UPLOAD_MAX_BYTES``."""
    if int(uploaded_file.size or 0) > EXTERNAL_UPLOAD_MAX_BYTES:
        _raise_external_upload_file_too_large()


def _persist_uploaded_file_to_temp(uploaded_file: UploadedFile) -> Path:
    """Stream upload to disk, enforcing the byte limit on actual chunk sizes."""
    fd, tmp_path_str = tempfile.mkstemp(prefix="external-upload-", suffix=".pdf")
    os_close(fd)
    tmp_path = Path(tmp_path_str)
    total = 0
    try:
        with tmp_path.open("wb") as handle:
            for chunk in uploaded_file.chunks():
                total += len(chunk)
                if total > EXTERNAL_UPLOAD_MAX_BYTES:
                    _raise_external_upload_file_too_large()
                handle.write(chunk)
    except DomainError:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        uploaded_file.seek(0)
    return tmp_path


def _validate_external_upload_pdf_file(path: Path) -> None:
    try:
        reader = PdfReader(str(path))
        if len(reader.pages) < 1:
            raise DomainError(
                domain_message("other.domain.external_upload_invalid_or_empty_pdf"),
                api_message_key="other.domain.external_upload_invalid_or_empty_pdf",
            )
    except DomainError:
        raise
    except Exception as exc:
        raise DomainError(
            domain_message("other.domain.external_upload_invalid_or_empty_pdf"),
            api_message_key="other.domain.external_upload_invalid_or_empty_pdf",
        ) from exc


@transaction.atomic
def _register_external_upload_pdf_pending(
    *,
    medical_document_id: uuid.UUID,
    uploaded_file: UploadedFile,
    actor_user_id: uuid.UUID,
) -> ExternalPdfAttachment:
    """Phase A: validate PDF and persist ``ExternalPdfAttachment`` as ``PENDING_UPLOAD``.

    HiDrive upload must run **after** this transaction commits so a rollback cannot
    leave orphan cloud objects.
    """
    try:
        actor = StaffUser.objects.get(id=actor_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    _assert_staff_user_may_act_on_external_upload(actor=actor)

    _assert_uploaded_file_within_byte_limit(uploaded_file)

    try:
        medical_document = MedicalDocument.objects.select_for_update().get(
            id=medical_document_id
        )
    except MedicalDocument.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.medical_document_not_found"),
            api_message_key="other.api.medical_document_not_found",
        ) from exc
    if medical_document.source_type != MedicalDocumentSourceType.EXTERNAL_UPLOAD:
        raise DomainError(
            domain_message("other.domain.external_upload_not_external_source"),
            api_message_key="other.domain.external_upload_not_external_source",
        )

    if (uploaded_file.content_type or "").lower() not in {
        "application/pdf",
        "application/x-pdf",
    }:
        raise DomainError(
            domain_message("other.domain.external_upload_invalid_content_type"),
            api_message_key="other.domain.external_upload_invalid_content_type",
        )

    local_tmp: Path | None = None
    try:
        local_tmp = _persist_uploaded_file_to_temp(uploaded_file)
        with local_tmp.open("rb") as handle:
            if handle.read(4) != b"%PDF":
                raise DomainError(
                    domain_message("other.domain.external_upload_not_pdf"),
                    api_message_key="other.domain.external_upload_not_pdf",
                )
        _validate_external_upload_pdf_file(local_tmp)
    finally:
        if local_tmp is not None:
            local_tmp.unlink(missing_ok=True)

    safe_filename = _sanitize_external_upload_filename(uploaded_file.name)
    queue_entry_id = medical_document.queue_entry_id
    remote_path = (
        f"{hidrive_incoming_dir()}/external-upload/{queue_entry_id}/{safe_filename}"
    )

    attachment, _ = ExternalPdfAttachment.objects.update_or_create(
        medical_document_id=medical_document_id,
        hidrive_remote_path=remote_path,
        defaults={
            "status": ExternalPdfStatus.PENDING_UPLOAD,
            "original_filename": safe_filename,
        },
    )
    return attachment


def _upload_external_pdf_attachment_to_hidrive(
    *,
    attachment_id: uuid.UUID,
    uploaded_file: UploadedFile,
) -> None:
    """Phase B: upload bytes to HiDrive (outside any enclosing DB transaction)."""
    try:
        attachment = ExternalPdfAttachment.objects.get(id=attachment_id)
    except ExternalPdfAttachment.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.domain.external_upload_attachment_not_found"),
            api_message_key="other.domain.external_upload_attachment_not_found",
        ) from exc

    if attachment.status == ExternalPdfStatus.MATCHED:
        return
    if attachment.status != ExternalPdfStatus.PENDING_UPLOAD:
        raise DomainError(
            domain_message("other.api.server_error"),
            api_message_key="other.api.server_error",
        )

    remote_path = attachment.hidrive_remote_path
    local_tmp: Path | None = None
    cleanup_tmp = False
    try:
        temp_path_callable = getattr(uploaded_file, "temporary_file_path", None)
        if callable(temp_path_callable):
            local_tmp = Path(temp_path_callable())
            if local_tmp.stat().st_size > EXTERNAL_UPLOAD_MAX_BYTES:
                _raise_external_upload_file_too_large()
        else:
            local_tmp = _persist_uploaded_file_to_temp(uploaded_file)
            cleanup_tmp = True
        get_hidrive_adapter().upload(remote_path=remote_path, local_path=local_tmp)
    except (HiDriveApiError, HiDriveAuthError) as exc:
        with transaction.atomic():
            ExternalPdfAttachment.objects.filter(
                id=attachment_id,
                status=ExternalPdfStatus.PENDING_UPLOAD,
            ).update(status=ExternalPdfStatus.UPLOAD_FAILED)
        raise DomainError(
            domain_message("other.api.server_error"),
            api_message_key="other.api.server_error",
        ) from exc
    finally:
        if cleanup_tmp and local_tmp is not None:
            local_tmp.unlink(missing_ok=True)


@transaction.atomic
def _mark_external_pdf_attachment_matched_after_hidrive(
    *, attachment_id: uuid.UUID
) -> None:
    """Phase C (part 1): flip ``PENDING_UPLOAD`` → ``MATCHED`` after HiDrive succeeded."""
    attachment = ExternalPdfAttachment.objects.select_for_update().get(id=attachment_id)
    if attachment.status == ExternalPdfStatus.PENDING_UPLOAD:
        attachment.status = ExternalPdfStatus.MATCHED
        attachment.save(update_fields=["status"])
    elif attachment.status != ExternalPdfStatus.MATCHED:
        raise DomainError(
            domain_message("other.api.server_error"),
            api_message_key="other.api.server_error",
        )


def upload_external_pdf_to_incoming(
    *,
    medical_document_id: uuid.UUID,
    uploaded_file: UploadedFile,
    actor_user_id: uuid.UUID,
) -> ExternalPdfAttachment:
    """Validate PDF, commit DB intent, upload to HiDrive, then mark ``MATCHED``.

    Split into phases so HiDrive I/O is not inside the same DB transaction as draft
    selection (see ``medical_external_upload_upload_view``). Callers that also bind the
    draft should invoke ``select_external_upload_attachment_for_draft`` afterward, or
    ``create_external_upload_pdf_and_bind_draft`` for the full create→upload→bind chain.
    """
    attachment = _register_external_upload_pdf_pending(
        medical_document_id=medical_document_id,
        uploaded_file=uploaded_file,
        actor_user_id=actor_user_id,
    )
    _upload_external_pdf_attachment_to_hidrive(
        attachment_id=attachment.id,
        uploaded_file=uploaded_file,
    )
    _mark_external_pdf_attachment_matched_after_hidrive(attachment_id=attachment.id)
    attachment.refresh_from_db()
    return attachment


def get_single_medical_document_for_queue_entry(
    *, queue_entry_id: uuid.UUID
) -> MedicalDocument:
    """Return the medical document for ``queue_entry_id`` if exactly one exists.

    Raises ``MedicalDocument.DoesNotExist`` when there is none. Raises
    :class:`~apps.core.exceptions.DomainError` when more than one row exists
    (one-to-one invariant broken) so callers never hit ``MultipleObjectsReturned``.
    """
    rows = list(
        MedicalDocument.objects.filter(queue_entry_id=queue_entry_id).order_by(
            "created_at"
        )[:2]
    )
    if not rows:
        raise MedicalDocument.DoesNotExist(
            "MedicalDocument matching query does not exist."
        )
    if len(rows) > 1:
        raise DomainError(
            domain_message(
                "other.domain.external_upload_multiple_medical_documents_for_queue_entry"
            ),
            api_message_key="other.domain.external_upload_multiple_medical_documents_for_queue_entry",
        )
    return rows[0]


@transaction.atomic
def create_external_upload_medical_document(
    *,
    queue_entry_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
) -> MedicalDocument:
    """Create or return the EXTERNAL_UPLOAD medical document for a queue entry.

    Idempotent on ``queue_entry_id``. If a document already exists with another
    ``source_type``, raises ``DomainError``.

    Requires a ``PatientIntakeForm`` linked to the entry with ``form_status`` in
    ``{SUBMITTED, REOPENED}`` (reopened = reception corrections before re-submit).

    On first successful create, inserts version ``1`` as ``DRAFT`` with empty
    ``medical_payload`` and default ``pdf_generation_status=PENDING`` (no local PDF
    until publish pipeline materializes it).

    ``created_by_user_id`` must refer to an existing :class:`~apps.users.models.StaffUser`
    with role **Reception**, **Admin**, or **Manager** (defense in depth; the HTTP
    entrypoint should already enforce ``require_auth`` for the intended role).

    After resolving the document row, the implementation takes a
    ``SELECT … FOR UPDATE`` on ``MedicalDocument`` for the remainder of the
    transaction. The locked row is not “used” for business reads beyond holding
    the lock: it serializes concurrent callers (duplicate HTTP requests,
    background workers) so bootstrap of draft v1 and in-place document fields
    cannot interleave on the same document.
    """
    try:
        actor = StaffUser.objects.get(id=created_by_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    _assert_staff_user_may_act_on_external_upload(actor=actor)

    try:
        QueueEntry.objects.get(pk=queue_entry_id)
    except QueueEntry.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.queue_entry_not_found"),
            api_message_key="other.api.queue_entry_not_found",
        ) from exc

    try:
        intake_form = PatientIntakeForm.objects.get(queue_entry_id=queue_entry_id)
    except PatientIntakeForm.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.queue_entry_or_intake_not_found"),
            api_message_key="other.api.queue_entry_or_intake_not_found",
        ) from exc

    if intake_form.form_status not in (
        IntakeStatus.SUBMITTED,
        IntakeStatus.REOPENED,
    ):
        raise DomainError(
            domain_message("other.domain.external_upload_intake_not_ready"),
            api_message_key="other.domain.external_upload_intake_not_ready",
        )

    try:
        medical_document, created = MedicalDocument.objects.get_or_create(
            queue_entry_id=queue_entry_id,
            defaults={
                "intake_form_id": intake_form.id,
                "source_type": MedicalDocumentSourceType.EXTERNAL_UPLOAD,
                "created_by_user_id": created_by_user_id,
                "updated_by_user_id": created_by_user_id,
            },
        )
    except IntegrityError as exc:
        try:
            medical_document = get_single_medical_document_for_queue_entry(
                queue_entry_id=queue_entry_id
            )
        except MedicalDocument.DoesNotExist:
            raise DomainError(
                domain_message("other.api.server_error"),
                api_message_key="other.api.server_error",
            ) from exc
        created = False

    if (
        not created
        and medical_document.source_type != MedicalDocumentSourceType.EXTERNAL_UPLOAD
    ):
        raise DomainError(
            domain_message("other.domain.medical_document_source_type_mismatch"),
            api_message_key="other.domain.medical_document_source_type_mismatch",
        )

    # Row lock on the document (not the queue entry): same rationale as in the
    # docstring — serialize bootstrap / updates for this medical_document id.
    medical_document = MedicalDocument.objects.select_for_update().get(
        pk=medical_document.id
    )

    if created:
        _bootstrap_external_upload_draft_v1(
            medical_document, created_by_user_id=created_by_user_id
        )
        doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
            id=medical_document.id
        )
        create_audit_event(
            event_type="MEDICAL_DOCUMENT_CREATED",
            actor_user_id=created_by_user_id,
            patient_id=doc.queue_entry.patient_id,
            medical_document_id=doc.id,
            context_clinic_site_id=doc.queue_entry.daily_queue.clinic_site_id,
            metadata={
                "queue_entry_id": str(queue_entry_id),
                "intake_form_id": str(intake_form.id),
                "source_type": doc.source_type,
                **assigned_doctor_audit_metadata(doc),
            },
        )
        return doc

    if not MedicalDocumentVersion.objects.filter(
        medical_document_id=medical_document.id
    ).exists():
        _bootstrap_external_upload_draft_v1(
            medical_document, created_by_user_id=created_by_user_id
        )

    return MedicalDocument.objects.select_related("queue_entry__daily_queue").get(
        id=medical_document.id
    )


def _hidrive_path_is_external_upload_prefix(path: str) -> bool:
    """True if *path* is under reception external-upload (incoming or processed)."""
    raw = (path or "").replace("\\", "/").strip()
    if not raw:
        return False
    if not raw.startswith("/"):
        raw = "/" + raw
    parts: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in ("/", "", "."):
            continue
        if part == "..":
            # Reject paths that try to escape the expected subtree.
            if not parts:
                return False
            parts.pop()
            continue
        parts.append(part)
    p = "/" + "/".join(parts)
    inc = hidrive_incoming_dir()
    proc = hidrive_processed_dir()
    inc_prefix = f"{inc}/external-upload"
    proc_prefix = f"{proc}/external-upload"
    return (
        p == inc_prefix
        or p.startswith(f"{inc_prefix}/")
        or p == proc_prefix
        or p.startswith(f"{proc_prefix}/")
    )


@transaction.atomic
def select_external_upload_attachment_for_draft(
    *,
    medical_document_id: uuid.UUID,
    attachment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> MedicalDocumentVersion:
    """Bind the current DRAFT to an ``ExternalPdfAttachment`` (MATCHED or ACCEPTED).

    Updates audit fields on the draft and clears any prior local PDF path/checksum
    when the operator changes selection. Does not download from HiDrive, does not
    change attachment status, and does not enqueue outbox work.
    """
    try:
        actor = StaffUser.objects.get(id=actor_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    _assert_staff_user_may_act_on_external_upload(actor=actor)

    try:
        medical_document = MedicalDocument.objects.select_for_update().get(
            id=medical_document_id
        )
    except MedicalDocument.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.medical_document_not_found"),
            api_message_key="other.api.medical_document_not_found",
        ) from exc
    if medical_document.source_type != MedicalDocumentSourceType.EXTERNAL_UPLOAD:
        raise DomainError(
            domain_message("other.domain.external_upload_not_external_source"),
            api_message_key="other.domain.external_upload_not_external_source",
        )

    draft_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.DRAFT,
        )
        .order_by("-version_no")
        .first()
    )
    if draft_version is None:
        raise DomainError(
            domain_message("other.domain.external_upload_no_active_draft"),
            api_message_key="other.domain.external_upload_no_active_draft",
        )

    try:
        attachment = ExternalPdfAttachment.objects.select_for_update().get(
            id=attachment_id,
            medical_document_id=medical_document_id,
        )
    except ExternalPdfAttachment.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.domain.external_upload_attachment_not_found"),
            api_message_key="other.domain.external_upload_attachment_not_found",
        ) from exc

    if attachment.status not in (
        ExternalPdfStatus.MATCHED,
        ExternalPdfStatus.ACCEPTED,
    ):
        raise DomainError(
            domain_message("other.domain.external_upload_attachment_invalid_status"),
            api_message_key="other.domain.external_upload_attachment_invalid_status",
        )

    if not _hidrive_path_is_external_upload_prefix(attachment.hidrive_remote_path):
        raise DomainError(
            domain_message("other.domain.external_upload_attachment_path_invalid"),
            api_message_key="other.domain.external_upload_attachment_path_invalid",
        )

    now = timezone.now()
    draft_version.external_selected_attachment_id = attachment.id
    draft_version.external_original_filename = attachment.original_filename
    draft_version.external_uploaded_by_user_id = actor_user_id
    draft_version.external_uploaded_at = now
    draft_version.pdf_local_path = None
    draft_version.pdf_checksum_sha256 = None
    draft_version.pdf_generation_status = PdfStatus.PENDING
    draft_version.save(
        update_fields=[
            "external_selected_attachment",
            "external_original_filename",
            "external_uploaded_by_user",
            "external_uploaded_at",
            "pdf_local_path",
            "pdf_checksum_sha256",
            "pdf_generation_status",
        ]
    )
    return draft_version


def create_external_upload_pdf_and_bind_draft(
    *,
    queue_entry_id: uuid.UUID,
    uploaded_file: UploadedFile,
    actor_user_id: uuid.UUID,
) -> tuple[MedicalDocument, ExternalPdfAttachment, MedicalDocumentVersion]:
    """Create or resolve EXTERNAL_UPLOAD document, upload PDF, bind active DRAFT.

    Thin wrapper around ``create_external_upload_medical_document`` →
    ``upload_external_pdf_to_incoming`` → ``select_external_upload_attachment_for_draft``.
    There is still **no** single enclosing ``transaction.atomic``: HiDrive I/O sits
    between DB commits (see those functions' docstrings). Shared by HTML hub and
    multipart API upload endpoint.
    """
    document = create_external_upload_medical_document(
        queue_entry_id=queue_entry_id,
        created_by_user_id=actor_user_id,
    )
    attachment = upload_external_pdf_to_incoming(
        medical_document_id=document.id,
        uploaded_file=uploaded_file,
        actor_user_id=actor_user_id,
    )
    draft_version = select_external_upload_attachment_for_draft(
        medical_document_id=document.id,
        attachment_id=attachment.id,
        actor_user_id=actor_user_id,
    )
    return document, attachment, draft_version


def _validate_paper_intake_authorization_reason(reason: str) -> str:
    text = (reason or "").strip()
    if len(text) < PAPER_INTAKE_AUTH_REASON_MIN_LEN:
        raise DomainError(
            domain_message("other.api.paper_intake_authorization_reason_required"),
            api_message_key="other.api.paper_intake_authorization_reason_required",
        )
    if len(text) > PAPER_INTAKE_AUTH_REASON_MAX_LEN:
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
        if timezone.now() < entry.appointment_time + timedelta(
            hours=PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT
        ):
            _min_h = PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT
            raise DomainError(
                domain_message(
                    "other.domain.paper_intake_authorization_too_early",
                    hours=_min_h,
                ),
                api_message_key="other.domain.paper_intake_authorization_too_early",
                api_message_params={"hours": _min_h},
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
        if timezone.now() < queue_entry.appointment_time + timedelta(
            hours=PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT
        ):
            _min_h = PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT
            raise DomainError(
                domain_message(
                    "other.domain.paper_intake_earliest_after_appointment",
                    hours=_min_h,
                ),
                api_message_key="other.domain.paper_intake_earliest_after_appointment",
                api_message_params={"hours": _min_h},
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


def begin_pending_revision_from_published(
    *,
    medical_document: MedicalDocument,
    actor_user_id: uuid.UUID,
) -> MedicalDocumentVersion:
    """
    Create a pending DRAFT cloned from the published version.

    Caller must hold ``MedicalDocument`` under ``select_for_update``.
    """
    if medical_document.status != MedicalDocStatus.PUBLISHED:
        raise DomainError(
            domain_message("other.domain.edit_session_document_read_only"),
            api_message_key="other.domain.edit_session_document_read_only",
        )
    if medical_document.has_pending_revision:
        pending = (
            MedicalDocumentVersion.objects.filter(
                medical_document_id=medical_document.id,
                version_status=DocVersionStatus.DRAFT,
            )
            .order_by("-version_no")
            .first()
        )
        if pending is not None:
            return pending
        raise DomainError(
            domain_message("other.api.no_pending_revision_to_discard"),
            api_message_key="other.api.no_pending_revision_to_discard",
        )

    pub_no = medical_document.published_version_no
    if pub_no is None:
        raise DomainError(
            domain_message("other.api.no_version_to_preview"),
            api_message_key="other.api.no_version_to_preview",
        )

    published_version = MedicalDocumentVersion.objects.get(
        medical_document_id=medical_document.id,
        version_no=pub_no,
        version_status=DocVersionStatus.PUBLISHED,
    )
    if published_version.local_pdf_deleted_at is not None:
        raise DomainError(
            domain_message("other.domain.republish_after_retention_not_allowed"),
            api_message_key="other.domain.republish_after_retention_not_allowed",
        )

    next_version_no = (
        MedicalDocumentVersion.objects.filter(
            medical_document_id=medical_document.id
        ).aggregate(max_no=Max("version_no"))["max_no"]
        or 0
    ) + 1

    created_version = MedicalDocumentVersion.objects.create(
        medical_document_id=medical_document.id,
        version_no=next_version_no,
        version_status=DocVersionStatus.DRAFT,
        medical_payload_schema_version=published_version.medical_payload_schema_version,
        medical_payload=published_version.medical_payload,
        diagnosis_code=published_version.diagnosis_code,
        procedure_code=published_version.procedure_code,
    )

    medical_document.has_pending_revision = True
    medical_document.draft_revision += 1
    medical_document.updated_by_user_id = actor_user_id
    medical_document.save(
        update_fields=[
            "has_pending_revision",
            "draft_revision",
            "updated_by_user",
            "updated_at",
        ]
    )
    create_audit_event(
        event_type="DOCUMENT_REVISION_STARTED",
        actor_user_id=actor_user_id,
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
    return created_version


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
    if is_published_doc and not medical_document.has_pending_revision:
        if intent == SAVE_DRAFT_INTENT_AMEND:
            raise DomainError(
                domain_message("other.api.amend_requires_edit_session"),
                api_message_key="other.api.amend_requires_edit_session",
            )
        raise DomainError(
            domain_message("other.api.amend_intent_required"),
            api_message_key="other.api.amend_intent_required",
        )
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
    clear_fields = clear_edit_session_lock_fields(medical_document)
    medical_document.save(
        update_fields=[
            "has_pending_revision",
            "updated_by_user",
            "updated_at",
            *clear_fields,
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


_PUBLICATION_PIPELINE_OUTBOX_TYPES = (
    OutboxEventType.GENERATE_PDF,
    OutboxEventType.HIDRIVE_UPLOAD,
    OutboxEventType.SMS_SEND,
)
_PUBLICATION_PIPELINE_OUTBOX_STATUSES = (
    OutboxStatus.PENDING,
    OutboxStatus.PROCESSING,
    OutboxStatus.FAILED,
)


def _published_version_with_pipeline_in_progress(
    *,
    medical_document_id: uuid.UUID,
) -> MedicalDocumentVersion | None:
    return (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.PUBLISHED,
            outbox_events__event_type__in=_PUBLICATION_PIPELINE_OUTBOX_TYPES,
            outbox_events__status__in=_PUBLICATION_PIPELINE_OUTBOX_STATUSES,
        )
        .order_by("-version_no")
        .first()
    )


def _resolve_publish_against_pipeline_in_progress(
    *,
    medical_document_id: uuid.UUID,
    draft_version: MedicalDocumentVersion | None,
    latest_draft_version_no: int | None,
) -> MedicalDocumentVersion | None:
    """
    When a published version still has outbox pipeline work:
    - return that version for same-version idempotent publish retries;
    - block publishing a newer draft revision while the prior version's pipeline runs.
    """
    in_progress_version = _published_version_with_pipeline_in_progress(
        medical_document_id=medical_document_id
    )
    if not in_progress_version:
        return None
    if (
        draft_version is not None
        and draft_version.version_no > in_progress_version.version_no
    ):
        raise DomainError(
            domain_message("other.domain.publication_pipeline_in_progress"),
            api_message_key="other.domain.publication_pipeline_in_progress",
        )
    if latest_draft_version_no is None or (
        in_progress_version.version_no >= latest_draft_version_no
    ):
        return in_progress_version
    return None


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

    try:
        actor = StaffUser.objects.get(id=published_by_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    _assert_staff_user_may_publish_medical_document(actor=actor)

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

    latest_draft_version_no = MedicalDocumentVersion.objects.filter(
        medical_document_id=medical_document_id,
        version_status=DocVersionStatus.DRAFT,
    ).aggregate(max_no=Max("version_no"))["max_no"]

    draft_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.DRAFT,
        )
        .order_by("-version_no")
        .first()
    )
    in_progress_version = _resolve_publish_against_pipeline_in_progress(
        medical_document_id=medical_document_id,
        draft_version=draft_version,
        latest_draft_version_no=latest_draft_version_no,
    )
    if in_progress_version is not None:
        return in_progress_version

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
    clear_fields = clear_edit_session_lock_fields(medical_document)
    medical_document.save(
        update_fields=[
            "status",
            "current_version_no",
            "published_version_no",
            "has_pending_revision",
            "last_published_at",
            "updated_by_user",
            "updated_at",
            *clear_fields,
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
def publish_external_upload_version(
    *,
    medical_document_id: uuid.UUID,
    publish_request_id: uuid.UUID,
    published_by_user_id: uuid.UUID,
    publish_locale: str,
    resend_sms: bool = False,
    now: datetime | None = None,
) -> MedicalDocumentVersion:
    """Publish latest EXTERNAL_UPLOAD draft; enqueue ``GENERATE_PDF`` like :func:`publish_document_version`.

    Skips Befund medical_payload validation; requires the draft to reference
    ``external_selected_attachment``. Sets ``external_verified_*`` to the publisher.
    """
    try:
        actor = StaffUser.objects.get(id=published_by_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    _assert_staff_user_may_act_on_external_upload(actor=actor)

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
    if medical_document.source_type != MedicalDocumentSourceType.EXTERNAL_UPLOAD:
        raise DomainError(
            domain_message("other.domain.external_upload_not_external_source"),
            api_message_key="other.domain.external_upload_not_external_source",
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

    latest_draft_version_no = MedicalDocumentVersion.objects.filter(
        medical_document_id=medical_document_id,
        version_status=DocVersionStatus.DRAFT,
    ).aggregate(max_no=Max("version_no"))["max_no"]

    draft_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.DRAFT,
        )
        .order_by("-version_no")
        .first()
    )
    in_progress_version = _resolve_publish_against_pipeline_in_progress(
        medical_document_id=medical_document_id,
        draft_version=draft_version,
        latest_draft_version_no=latest_draft_version_no,
    )
    if in_progress_version is not None:
        return in_progress_version

    if not draft_version:
        raise DomainError(
            domain_message("other.api.no_draft_before_publish"),
            api_message_key="other.api.no_draft_before_publish",
        )
    if draft_version.external_selected_attachment_id is None:
        raise DomainError(
            domain_message(
                "other.domain.external_upload_publish_no_attachment_selected"
            ),
            api_message_key="other.domain.external_upload_publish_no_attachment_selected",
        )

    draft_version.version_status = DocVersionStatus.PUBLISHED
    draft_version.publish_request_id = publish_request_id
    draft_version.publish_requested_by_user_id = published_by_user_id
    draft_version.publish_locale = publish_locale
    draft_version.published_by_user_id = published_by_user_id
    draft_version.published_at = requested_at
    draft_version.pdf_generation_status = PdfStatus.PENDING
    draft_version.external_verified_by_user_id = published_by_user_id
    draft_version.external_verified_at = requested_at
    draft_version.save(
        update_fields=[
            "version_status",
            "publish_request_id",
            "publish_requested_by_user",
            "publish_locale",
            "published_by_user",
            "published_at",
            "pdf_generation_status",
            "external_verified_by_user",
            "external_verified_at",
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
            "source_type": medical_document.source_type,
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
def start_external_upload_revision(
    *,
    medical_document_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> MedicalDocumentVersion:
    """Reception path: open a new DRAFT on a PUBLISHED EXTERNAL_UPLOAD document (amend / republish)."""
    try:
        actor = StaffUser.objects.get(id=actor_user_id)
    except StaffUser.DoesNotExist as exc:
        raise DomainError(
            domain_message("other.api.staff_user_not_found"),
            api_message_key="other.api.staff_user_not_found",
        ) from exc
    _assert_staff_user_may_act_on_external_upload(actor=actor)

    medical_document = MedicalDocument.objects.select_for_update().get(
        id=medical_document_id
    )
    if medical_document.source_type != MedicalDocumentSourceType.EXTERNAL_UPLOAD:
        raise DomainError(
            domain_message("other.domain.external_upload_not_external_source"),
            api_message_key="other.domain.external_upload_not_external_source",
        )
    if medical_document.status != MedicalDocStatus.PUBLISHED:
        raise DomainError(
            domain_message("other.domain.external_upload_revision_requires_published"),
            api_message_key="other.domain.external_upload_revision_requires_published",
        )
    if medical_document.has_pending_revision:
        raise DomainError(
            domain_message("other.domain.external_upload_revision_already_pending"),
            api_message_key="other.domain.external_upload_revision_already_pending",
        )
    if _published_version_with_pipeline_in_progress(
        medical_document_id=medical_document_id
    ):
        raise DomainError(
            domain_message("other.domain.publication_pipeline_in_progress"),
            api_message_key="other.domain.publication_pipeline_in_progress",
        )

    pub_no = medical_document.published_version_no
    if pub_no is not None:
        pub_ver = (
            MedicalDocumentVersion.objects.select_for_update()
            .filter(
                medical_document_id=medical_document_id,
                version_no=pub_no,
                version_status=DocVersionStatus.PUBLISHED,
            )
            .first()
        )
        if pub_ver is not None and pub_ver.local_pdf_deleted_at is not None:
            raise DomainError(
                domain_message("other.domain.republish_after_retention_not_allowed"),
                api_message_key="other.domain.republish_after_retention_not_allowed",
            )

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
        medical_payload_schema_version=1,
        medical_payload={},
    )

    medical_document.has_pending_revision = True
    medical_document.updated_by_user_id = actor_user_id
    medical_document.save(
        update_fields=["has_pending_revision", "updated_by_user", "updated_at"]
    )
    create_audit_event(
        event_type="DOCUMENT_REVISION_STARTED",
        actor_user_id=actor_user_id,
        patient_id=medical_document.queue_entry.patient_id,
        medical_document_id=medical_document.id,
        context_clinic_site_id=medical_document.queue_entry.daily_queue.clinic_site_id,
        metadata={
            "medical_document_version_id": str(created_version.id),
            "version_no": created_version.version_no,
            "previous_published_version_no": medical_document.published_version_no,
            "source_type": medical_document.source_type,
            **assigned_doctor_audit_metadata(medical_document),
        },
    )
    return created_version


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


def parse_doctor_work_queue_list_params(
    get_params: Any, *, user: Any = None
) -> dict[str, Any]:
    """
    Parse GET parameters for doctor work queue (HTML + API list).

    Doctors: ``scope`` is always ``all``; ``published_by_user_id`` is ignored.
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
    published_by_user_id: uuid.UUID | None = None
    scope = (get_params.get("scope") or "all").strip()
    if scope not in {"all", "mine", "published_by_me", "in_revision"}:
        scope = "all"
    is_doctor_only = (
        user is not None
        and getattr(user, "is_doctor", False)
        and not _is_admin_or_manager_medical_oversight(user)
    )
    if is_doctor_only:
        scope = "all"
    else:
        raw_pub_id = (get_params.get("published_by_user_id") or "").strip()
        if raw_pub_id:
            try:
                published_by_user_id = uuid.UUID(raw_pub_id)
            except (ValueError, TypeError):
                published_by_user_id = None
    sort = (get_params.get("sort") or "date").strip().lower()
    if sort not in {"date", "patient"}:
        sort = "date"
    order = (get_params.get("order") or "desc").strip().lower()
    if order not in {"asc", "desc"}:
        order = "desc"
    page = safe_parse_positive_int(get_params.get("page"), default=1, maximum=10_000)
    page_size = parse_page_size(get_params.get("page_size"))
    return {
        "status": status,
        "queue_date": queue_date,
        "patient_search": patient_search,
        "published_by_user_id": published_by_user_id,
        "scope": scope,
        "sort": sort,
        "order": order,
        "page": page,
        "page_size": page_size,
    }


def list_doctor_work_queue(
    *,
    status: str | None = None,
    queue_date: date | None = None,
    patient_search: str | None = None,
    published_by_user_id: uuid.UUID | None = None,
    scope: str = "all",
    sort: str = "date",
    order: str = "desc",
    user: Any = None,
    page: int = 1,
    page_size: int = DEFAULT_LIST_LIMIT,
) -> tuple[list[dict[str, Any]], int]:
    """
    List doctor work queue using ``QueueEntry`` as source of truth.

    Visibility states:
    - A: digital intake submitted/reopened
    - B: paper intake authorized, no medical document yet
    - C: paper intake completed with medical document created from paper flow

    Cancelled queue entries (``entry_status=CANCELLED``) are always excluded.
    """
    submitted_or_reopened_intake_exists = PatientIntakeForm.objects.filter(
        queue_entry_id=OuterRef("pk"),
        form_status__in=(IntakeStatus.SUBMITTED, IntakeStatus.REOPENED),
    )
    paper_authorization_exists = PaperIntakeAuthorization.objects.filter(
        queue_entry_id=OuterRef("pk")
    )
    qs = QueueEntry.objects.select_related(
        "patient",
        "daily_queue",
        "intake_form",
        "medical_document",
    ).annotate(
        has_submitted_or_reopened_intake=Exists(submitted_or_reopened_intake_exists),
        has_paper_intake_authorization=Exists(paper_authorization_exists),
    )
    qs = qs.exclude(entry_status=QueueEntryStatus.CANCELLED)
    qs = qs.filter(
        Q(has_submitted_or_reopened_intake=True)
        | Q(
            entry_status=QueueEntryStatus.WAITING,
            medical_document__isnull=True,
            has_paper_intake_authorization=True,
        )
        | Q(
            entry_status=QueueEntryStatus.PAPER_INTAKE_COMPLETED,
            medical_document__source_type=MedicalDocumentSourceType.PAPER_INTAKE,
        )
    )
    if user is not None:
        is_oversight = _is_admin_or_manager_medical_oversight(user)
        if is_oversight:
            personal = Q(medical_document__created_by_user_id=user.id) | Q(
                daily_queue__assigned_doctor_id=user.id
            )
            published_by_user_exists = Exists(
                MedicalDocumentVersion.objects.filter(
                    medical_document__queue_entry_id=OuterRef("pk"),
                    version_status=DocVersionStatus.PUBLISHED,
                    published_by_user_id=user.id,
                )
            )
            qs = qs.annotate(has_published_by_user=published_by_user_exists)
            personal = personal | Q(has_published_by_user=True)
            in_revision_q = Q(
                medical_document__status=MedicalDocStatus.PUBLISHED,
                medical_document__has_pending_revision=True,
            )
            if scope == "mine":
                qs = qs.filter(personal)
            elif scope == "published_by_me":
                qs = qs.filter(has_published_by_user=True)
            elif scope == "in_revision":
                qs = qs.filter(in_revision_q)
        else:
            qs = qs.filter(_doctor_work_queue_visibility_q(user=user))
            if scope == "in_revision":
                qs = qs.filter(
                    medical_document__status=MedicalDocStatus.PUBLISHED,
                    medical_document__has_pending_revision=True,
                )
    if status:
        if status == MedicalDocStatus.DRAFT:
            qs = qs.filter(
                Q(medical_document__status=MedicalDocStatus.DRAFT)
                | Q(medical_document__has_pending_revision=True)
            )
        else:
            qs = qs.filter(medical_document__status=status)
    if queue_date is not None:
        qs = qs.filter(daily_queue__queue_date=queue_date)
    if patient_search and patient_search.strip():
        term = patient_search.strip()
        qs = qs.filter(
            Q(patient__last_name__icontains=term)
            | Q(patient__first_name__icontains=term)
        )
    if published_by_user_id is not None:
        publisher_row_exists = Exists(
            MedicalDocumentVersion.objects.filter(
                medical_document__queue_entry_id=OuterRef("pk"),
                version_status=DocVersionStatus.PUBLISHED,
                published_by_user_id=published_by_user_id,
            )
        )
        qs = qs.filter(publisher_row_exists)
    unpublished_q = _doctor_queue_unpublished_q()
    qs = qs.annotate(
        _doctor_queue_pub_group=Case(
            When(unpublished_q, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )
    if sort == "patient":
        if order == "asc":
            qs = qs.order_by(
                "_doctor_queue_pub_group",
                "patient__last_name",
                "patient__first_name",
                "id",
            )
        else:
            qs = qs.order_by(
                "_doctor_queue_pub_group",
                "-patient__last_name",
                "-patient__first_name",
                "-id",
            )
    elif order == "asc":
        qs = qs.order_by(
            "_doctor_queue_pub_group",
            F("doctor_list_sort_at").asc(nulls_last=True),
            F("daily_queue__queue_date").asc(nulls_last=True),
            "id",
        )
    else:
        qs = qs.order_by(
            "_doctor_queue_pub_group",
            F("doctor_list_sort_at").desc(nulls_last=True),
            F("daily_queue__queue_date").desc(nulls_last=True),
            "-id",
        )
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    entries = list(qs[start:end])
    if not entries:
        return [], total
    queue_entry_ids = [entry.id for entry in entries]
    docs = (
        MedicalDocument.objects.filter(queue_entry_id__in=queue_entry_ids)
        .select_related("locked_by_user", "updated_by_user")
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
    published_by_display_by_doc_id: dict[uuid.UUID, str] = {}
    if doc_ids:
        published_versions = (
            MedicalDocumentVersion.objects.filter(
                medical_document_id__in=doc_ids,
                version_status=DocVersionStatus.PUBLISHED,
            )
            .select_related("published_by_user")
            .order_by("medical_document_id", "-version_no")
        )
        for ver in published_versions:
            if ver.medical_document_id in published_by_display_by_doc_id:
                continue
            published_by_display_by_doc_id[ver.medical_document_id] = (
                staff_user_display_name(ver.published_by_user)
            )
    list_items = [
        _serialize_doctor_work_queue_row(
            entry=entry,
            doc=doc_by_entry.get(entry.id),
            intake_form=getattr(entry, "intake_form", None),
            published_by_display_by_doc_id=published_by_display_by_doc_id,
            user=user,
        )
        for entry in entries
    ]
    return list_items, total


def _doctor_list_unpublished_sla_effective_start(
    entry: QueueEntry,
    intake_form: PatientIntakeForm | None,
) -> datetime | None:
    """Start of the unpublished SLA window: list sort key, then intake submit, then entry create."""
    t = entry.doctor_list_sort_at
    if t is None and intake_form is not None and intake_form.submitted_at:
        t = intake_form.submitted_at
    if t is None:
        t = entry.created_at
    return t


def _doctor_list_unpublished_sla_urgency_and_deadline(
    *,
    entry: QueueEntry,
    doc: MedicalDocument | None,
    intake_form: PatientIntakeForm | None,
    paper_intake_action_required: bool,
    now: datetime,
) -> tuple[float, str | None]:
    """
    ``(urgency, sla_deadline_iso)`` for doctor list unpublished SLA row tint.

    Urgency is 0..1. Deadline ISO is set only when urgency > 0 and not paper state B
    (same rules as prior separate deadline field).
    """
    if (
        doc is not None
        and doc.status == MedicalDocStatus.PUBLISHED
        and not doc.has_pending_revision
    ):
        return 0.0, None
    unpublished = (
        doc is None
        or doc.status == MedicalDocStatus.DRAFT
        or bool(doc and doc.has_pending_revision)
    )
    if not unpublished:
        return 0.0, None
    if paper_intake_action_required:
        return 1.0, None
    t_eff = _doctor_list_unpublished_sla_effective_start(entry, intake_form)
    if t_eff is None:
        return 0.0, None
    elapsed = now - t_eff
    if elapsed < timedelta(0):
        elapsed = timedelta(0)
    window = timedelta(hours=DOCTOR_LIST_UNPUBLISHED_SLA_HOURS)
    ratio = min(1.0, float(elapsed.total_seconds() / window.total_seconds()))
    deadline_at: str | None = None
    if ratio > 0:
        deadline_at = (t_eff + window).isoformat()
    return ratio, deadline_at


def _serialize_doctor_work_queue_row(
    *,
    entry: QueueEntry,
    doc: MedicalDocument | None,
    intake_form: PatientIntakeForm | None,
    published_by_display_by_doc_id: dict[uuid.UUID, str],
    user: Any,
) -> dict[str, Any]:
    """Serialize one doctor queue row (doc may be ``None`` for paper action-required state B)."""
    patient = entry.patient
    queue = entry.daily_queue
    versions = list(doc.versions.all())[:1] if doc else []
    latest = versions[0] if versions else None
    events_by_type = {}
    if latest:
        events_by_type = {e.event_type: e for e in latest.outbox_events.all()}
    hidrive_status = (
        outbox_event_stage_status(
            events_by_type.get("HIDRIVE_UPLOAD"),
            completed=bool(latest and latest.hidrive_sent),
        )
        if latest
        else None
    )
    sms_status = (
        outbox_event_stage_status(
            events_by_type.get("SMS_SEND"),
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
        and doc.locked_by_user_id != getattr(user, "id", None)
        and not _is_admin_or_manager_medical_oversight(user)
    )
    is_locked_by_self = bool(
        doc and locked_eff and doc.locked_by_user_id == getattr(user, "id", None)
    )
    row_has_open_befund_edit = bool(
        doc
        and (
            doc.status == MedicalDocStatus.DRAFT
            or (doc.status == MedicalDocStatus.PUBLISHED and doc.has_pending_revision)
        )
    )
    # Doctor list row tint: yellow = active edit lock on DRAFT or open revision.
    row_has_edit_semaphore = bool(row_has_open_befund_edit and locked_eff)
    # Active lock → who holds it (self or other). Expired lock / idle DRAFT →
    # last draft editor so stale ENTWURF rows are not "ownerless".
    editor_activity: str | None = None
    editor_username: str | None = None
    if row_has_open_befund_edit and doc is not None:
        if locked_eff and locked_name:
            editor_activity = "active"
            editor_username = locked_name
        else:
            updater = getattr(doc, "updated_by_user", None)
            if updater is None and doc.updated_by_user_id:
                updater = StaffUser.objects.filter(id=doc.updated_by_user_id).first()
            last_name = staff_user_display_name(updater) if updater else ""
            if last_name:
                editor_activity = "last"
                editor_username = last_name
    # Green row = published and outbound pipeline finished (same rules as list columns).
    row_is_fully_delivered = bool(
        doc
        and doc.status == MedicalDocStatus.PUBLISHED
        and not doc.has_pending_revision
        and work_queue_row_outbound_complete(
            version=latest,
            events_by_type=events_by_type,
        )
    )
    has_pending_revision = bool(doc and doc.has_pending_revision)
    published_version_no = doc.published_version_no if doc else None
    paper_intake_action_required = bool(
        doc is None and getattr(entry, "has_paper_intake_authorization", False)
    )
    now = timezone.now()
    row_unpublished_urgency, row_unpublished_sla_deadline_at = (
        _doctor_list_unpublished_sla_urgency_and_deadline(
            entry=entry,
            doc=doc,
            intake_form=intake_form,
            paper_intake_action_required=paper_intake_action_required,
            now=now,
        )
    )
    row_unpublished_sla_active = row_unpublished_urgency > 1e-9
    return {
        "document_id": str(doc.id) if doc else None,
        "queue_entry_id": str(entry.id),
        "intake_form_id": (
            str(intake_form.id)
            if intake_form is not None
            else str(doc.intake_form_id) if doc and doc.intake_form_id else None
        ),
        "patient": {
            "id": str(patient.id),
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth.isoformat(),
        },
        "queue_date": queue.queue_date.isoformat(),
        "status": doc.status if doc else "—",
        "published_by": published_by_display_by_doc_id.get(doc.id, "") if doc else "",
        "has_pending_revision": has_pending_revision,
        "published_version_no": published_version_no,
        "locked_by_username": locked_name,
        "locked_at": locked_at.isoformat() if locked_at else None,
        "is_locked_by_other": is_locked_by_other,
        "is_locked_by_self": is_locked_by_self,
        "editor_activity": editor_activity,
        "editor_username": editor_username,
        "row_is_published": is_published,
        "row_has_edit_semaphore": row_has_edit_semaphore,
        "row_is_fully_delivered": row_is_fully_delivered,
        "pdf_generation_status": latest.pdf_generation_status if latest else None,
        "hidrive_sent": latest.hidrive_sent if latest else False,
        "sms_sent": latest.sms_sent if latest else False,
        "hidrive_status": hidrive_status,
        "sms_status": sms_status,
        "processing_error_message": (
            latest_version_processing_error_message(latest) if latest else None
        ),
        "can_retry_processing": retryable_event is not None,
        "retry_event_status": retryable_event.status if retryable_event else None,
        "paper_intake_action_required": paper_intake_action_required,
        "row_unpublished_urgency": row_unpublished_urgency,
        "row_unpublished_sla_active": row_unpublished_sla_active,
        "row_unpublished_sla_deadline_at": row_unpublished_sla_deadline_at,
    }


def get_medical_document_context(
    *,
    medical_document_id: uuid.UUID,
    form_locale: str = "de-DE",
    user: Any = None,
    audit_context: DoctorAccessAuditContext | None = None,
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
        check_doctor_document_access(doc, user, audit_context=audit_context)
    latest_version = doc.versions.all()[:1]
    current_version = latest_version[0] if latest_version else None

    intake_form = getattr(doc, "intake_form", None)
    reception_note = (
        (intake_form.reception_note or "").strip() if intake_form is not None else ""
    )

    intake_summary: dict[str, Any]
    if doc.intake_form_id is None:
        patient = doc.queue_entry.patient
        intake_summary = {
            "consents": [],
            "body_map_data": [],
            "anamnesis_questions": [],
            "anamnesis_answers": [],
            "reception_note": "",
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
            "reception_note": reception_note,
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
                    events_by_type.get("HIDRIVE_UPLOAD"),
                    completed=current_version.hidrive_sent,
                ),
                "sms_status": outbox_event_stage_status(
                    events_by_type.get("SMS_SEND"),
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
                "revoked_at": (
                    current_version.revoked_at.isoformat()
                    if current_version.revoked_at
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
                    events_by_type.get("HIDRIVE_UPLOAD"),
                    completed=current_version.hidrive_sent,
                ),
                "sms_status": outbox_event_stage_status(
                    events_by_type.get("SMS_SEND"),
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
                "revoked_at": (
                    current_version.revoked_at.isoformat()
                    if current_version.revoked_at
                    else None
                ),
            }

    lock_eff, lock_name, lock_at = get_document_lock_state(doc)
    paper_payload = _paper_intake_authorization_context_for_document(doc)
    if doc.source_type == MedicalDocumentSourceType.PAPER_INTAKE:
        if paper_payload is None:
            raise DomainError(
                domain_message(
                    "other.domain.paper_intake_document_audit_snapshot_missing"
                ),
                api_message_key=(
                    "other.domain.paper_intake_document_audit_snapshot_missing"
                ),
            )
    return {
        "id": str(doc.id),
        "queue_entry_id": str(doc.queue_entry_id),
        "intake_form_id": str(doc.intake_form_id) if doc.intake_form_id else None,
        "source_type": doc.source_type,
        "status": doc.status,
        "current_version_no": doc.current_version_no,
        "published_version_no": doc.published_version_no,
        "has_pending_revision": doc.has_pending_revision,
        "draft_revision": int(doc.draft_revision or 0),
        "last_previewed_draft_revision": (
            int(doc.last_previewed_draft_revision)
            if doc.last_previewed_draft_revision is not None
            else None
        ),
        "last_published_at": (
            doc.last_published_at.isoformat() if doc.last_published_at else None
        ),
        "locked_by_user_id": (
            str(doc.locked_by_user_id) if doc.locked_by_user_id else None
        ),
        "locked_by_username": lock_name if lock_eff else None,
        "locked_at": lock_at.isoformat() if lock_at and lock_eff else None,
        "intake_summary": intake_summary,
        "paper_intake_authorization": paper_payload,
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
