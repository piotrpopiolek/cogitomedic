from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.utils import timezone

from apps.core.api_utils import safe_parse_positive_int
from apps.core.exceptions import DomainError, IdempotencyConflictError, StateTransitionError
from apps.medical.medical_payload_schemas import validate_medical_payload_complete_for_publish
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.intake.services import get_intake_form_context
from apps.medical.models import DocVersionStatus, MedicalDocStatus, MedicalDocument, MedicalDocumentVersion, PdfStatus
from apps.operations.services import create_audit_event
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.outbox.services import retry_outbox_event, _try_delete_file
from apps.reception.models import QueueEntry
from apps.users.models import StaffUser


def _assigned_doctor_metadata(medical_document: MedicalDocument) -> dict[str, str]:
    """Expose assigned doctor in audit metadata for GET /audit-events doctor filter."""
    aid = medical_document.queue_entry.daily_queue.assigned_doctor_id
    if aid is None:
        return {}
    return {"assigned_doctor_id": str(aid)}


def _event_status_to_stage_status(event: OutboxEvent | None, completed: bool) -> str:
    if completed:
        return "COMPLETED"
    if event is None:
        return "PENDING"
    if event.status in [OutboxStatus.PENDING, OutboxStatus.PROCESSING]:
        return event.status
    if event.status == OutboxStatus.PROCESSED:
        return "COMPLETED"
    return "FAILED"


def _latest_retryable_event(version: MedicalDocumentVersion) -> OutboxEvent | None:
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


def _latest_error_message(version: MedicalDocumentVersion) -> str | None:
    events = list(version.outbox_events.all())
    failed = [e for e in events if e.status in [OutboxStatus.FAILED, OutboxStatus.DEAD_LETTER] and (e.error_message or "").strip()]
    if not failed:
        return None
    failed.sort(key=lambda e: e.updated_at, reverse=True)
    return failed[0].error_message


def check_doctor_document_access(document: MedicalDocument, user: Any) -> None:
    """
    Raise ObjectDoesNotExist if user (doctor) does not have access.
    Access is granted if user is the author OR is assigned to the document's queue.
    ADMIN has access to all.
    """
    if user.is_admin_role:
        return
    if document.created_by_user_id == user.id:
        return
    if document.queue_entry.daily_queue.assigned_doctor_id == user.id:
        return
    raise ObjectDoesNotExist("Medical document not found.")

def check_doctor_queue_entry_access(queue_entry: QueueEntry, user: Any) -> None:
    """Raise ObjectDoesNotExist if user does not have access to the queue entry."""
    if user.is_admin_role:
        return
    if queue_entry.daily_queue.assigned_doctor_id == user.id:
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
        raise DomainError("Intake form does not belong to this queue entry.")
    if intake_form.form_status != IntakeStatus.SUBMITTED:
        raise DomainError("Intake form must be submitted.")
    medical_document, created = MedicalDocument.objects.get_or_create(
        queue_entry_id=queue_entry_id,
        defaults={
            "intake_form_id": intake_form_id,
            "created_by_user_id": created_by_user_id,
            "updated_by_user_id": created_by_user_id,
        },
    )
    doc = MedicalDocument.objects.select_related("queue_entry__daily_queue").get(id=medical_document.id)
    if created:
        meta = {
            "queue_entry_id": str(queue_entry_id),
            "intake_form_id": str(intake_form_id),
            **_assigned_doctor_metadata(doc),
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
    medical_document = MedicalDocument.objects.select_for_update().get(id=medical_document_id)

    latest_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(medical_document_id=medical_document_id)
        .order_by("-version_no")
        .first()
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
                **_assigned_doctor_metadata(medical_document),
            },
        )
        return latest_version

    next_version_no = (
        MedicalDocumentVersion.objects.filter(medical_document_id=medical_document_id).aggregate(
            max_no=Max("version_no")
        )["max_no"]
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
            **_assigned_doctor_metadata(medical_document),
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
        raise IdempotencyConflictError("publish_request_id is required for publish.")
    if not publish_locale:
        raise DomainError("publish_locale is required for publish.")

    requested_at = now or timezone.now()
    medical_document = MedicalDocument.objects.select_for_update().get(id=medical_document_id)

    same_request_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            publish_request_id=publish_request_id,
        )
        .first()
    )
    if same_request_version:
        if same_request_version.publish_locale and same_request_version.publish_locale != publish_locale:
            raise IdempotencyConflictError("publish_request_id already used with different publish_locale.")
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
            "No draft version available. Save a draft (PUT .../draft) with validated payload before publishing."
        )

    validate_medical_payload_complete_for_publish(draft_version.medical_payload, locale=publish_locale)

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
    medical_document.save(
        update_fields=[
            "status",
            "current_version_no",
            "last_published_at",
            "updated_by_user",
            "updated_at",
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
            **_assigned_doctor_metadata(medical_document),
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
    medical_document = MedicalDocument.objects.select_for_update().select_related(
        "queue_entry",
        "queue_entry__daily_queue",
    ).get(id=medical_document_id)

    current_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(
            medical_document_id=medical_document_id,
            version_status=DocVersionStatus.PUBLISHED,
            version_no=medical_document.current_version_no,
        )
        .select_related("medical_document", "medical_document__queue_entry", "medical_document__queue_entry__daily_queue")
        .first()
    )
    if not current_version:
        raise DomainError("No published version to revoke.")

    if current_version.revoked_at:
        return current_version

    now = timezone.now()
    _try_delete_file(current_version.pdf_local_path)

    update_fields = ["revoked_at", "pdf_local_path"]
    current_version.revoked_at = now
    current_version.pdf_local_path = None

    if current_version.hidrive_sent and current_version.sms_sent:
        current_version.local_pdf_deleted_at = now
        update_fields.append("local_pdf_deleted_at")

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
            **_assigned_doctor_metadata(medical_document),
        },
    )
    return current_version


def parse_medical_documents_list_params(get_params: Any) -> dict[str, Any]:
    """
    Parse GET parameters for medical documents list (work queue).
    Returns dict with status, queue_date, patient_search, page, page_size.
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
    page = safe_parse_positive_int(get_params.get("page"), default=1, maximum=10_000)
    page_size = safe_parse_positive_int(
        get_params.get("page_size"), default=20, maximum=200
    )
    return {
        "status": status,
        "queue_date": queue_date,
        "patient_search": patient_search,
        "page": page,
        "page_size": page_size,
    }


def list_medical_documents(
    *,
    status: str | None = None,
    queue_date: date | None = None,
    patient_search: str | None = None,
    user: Any = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[MedicalDocument], int]:
    """
    List medical documents for doctor work queue.
    If user is DOCTOR, returns only documents where user is author OR assigned to queue.
    """
    qs = (
        MedicalDocument.objects.select_related(
            "queue_entry",
            "queue_entry__patient",
            "queue_entry__daily_queue",
        )
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=MedicalDocumentVersion.objects.order_by("-version_no").prefetch_related(
                    Prefetch("outbox_events", queryset=OutboxEvent.objects.order_by("-created_at"))
                ),
            )
        )
        .order_by("-updated_at")
    )
    if not user.is_admin_role and user is not None:
        qs = qs.filter(
            Q(created_by_user_id=user.id) | Q(queue_entry__daily_queue__assigned_doctor_id=user.id)
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
    user: Any = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """
    List doctor work queue: queue entries with submitted intake (ankieta pacjenta).
    """
    qs = (
        PatientIntakeForm.objects.filter(form_status=IntakeStatus.SUBMITTED)
        .select_related("queue_entry", "queue_entry__patient", "queue_entry__daily_queue")
    )
    if not user.is_admin_role and user is not None:
        qs = qs.filter(
            Q(queue_entry__medical_document__created_by_user_id=user.id) | 
            Q(queue_entry__daily_queue__assigned_doctor_id=user.id)
        )
    if status:
        qs = qs.filter(
            queue_entry_id__in=MedicalDocument.objects.filter(status=status).values_list("queue_entry_id", flat=True)
        )
    if queue_date is not None:
        qs = qs.filter(queue_entry__daily_queue__queue_date=queue_date)
    if patient_search and patient_search.strip():
        term = patient_search.strip()
        qs = qs.filter(
            Q(queue_entry__patient__last_name__icontains=term)
            | Q(queue_entry__patient__first_name__icontains=term)
        )
    qs = qs.order_by("-queue_entry__daily_queue__queue_date", "-submitted_at")
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    intake_forms = list(qs[start:end])
    if not intake_forms:
        return [], total
    queue_entry_ids = [f.queue_entry_id for f in intake_forms]
    docs = (
        MedicalDocument.objects.filter(queue_entry_id__in=queue_entry_ids)
        .select_related("queue_entry")
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=MedicalDocumentVersion.objects.order_by("-version_no").prefetch_related(
                    Prefetch("outbox_events", queryset=OutboxEvent.objects.order_by("-created_at"))
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
        hidrive_status = _event_status_to_stage_status(
            events_by_type.get(OutboxEventType.HIDRIVE_UPLOAD),
            completed=bool(latest and latest.hidrive_sent),
        ) if latest else None
        sms_status = _event_status_to_stage_status(
            events_by_type.get(OutboxEventType.SMS_SEND),
            completed=bool(latest and latest.sms_sent),
        ) if latest else None
        retryable_event = _latest_retryable_event(latest) if latest else None
        list_items.append({
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
            "pdf_generation_status": latest.pdf_generation_status if latest else None,
            "hidrive_sent": latest.hidrive_sent if latest else False,
            "sms_sent": latest.sms_sent if latest else False,
            "hidrive_status": hidrive_status,
            "sms_status": sms_status,
            "processing_error_message": _latest_error_message(latest) if latest else None,
            "can_retry_processing": retryable_event is not None,
            "retry_event_status": retryable_event.status if retryable_event else None,
        })
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
        )
        .prefetch_related(
            Prefetch(
                "versions",
                queryset=MedicalDocumentVersion.objects.order_by("-version_no").prefetch_related(
                    Prefetch("outbox_events", queryset=OutboxEvent.objects.order_by("-created_at"))
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
                "selected_option_codes": (q.get("answer") or {}).get("selected_option_codes") or [],
                "free_text": (q.get("answer") or {}).get("free_text"),
            }
            for q in anamnesis_questions
        ],
        "patient": intake_context.get("patient"),
    }

    current_version_payload: dict[str, Any] | None = None
    if current_version:
        events_by_type = {e.event_type: e for e in current_version.outbox_events.all()}
        retryable_event = _latest_retryable_event(current_version)
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
            "hidrive_status": _event_status_to_stage_status(
                events_by_type.get(OutboxEventType.HIDRIVE_UPLOAD),
                completed=current_version.hidrive_sent,
            ),
            "sms_status": _event_status_to_stage_status(
                events_by_type.get(OutboxEventType.SMS_SEND),
                completed=current_version.sms_sent,
            ),
            "processing_error_message": _latest_error_message(current_version),
            "can_retry_processing": retryable_event is not None
            and (getattr(user, "is_admin_role", False) or getattr(user, "is_reception", False)),
            "publish_locale": current_version.publish_locale,
            "published_at": current_version.published_at.isoformat() if current_version.published_at else None,
        }

    return {
        "id": str(doc.id),
        "queue_entry_id": str(doc.queue_entry_id),
        "intake_form_id": str(doc.intake_form_id),
        "status": doc.status,
        "current_version_no": doc.current_version_no,
        "last_published_at": doc.last_published_at.isoformat() if doc.last_published_at else None,
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
    if not (actor.is_admin_role or actor.is_reception):
        raise DomainError("Only ADMIN or RECEPTION can retry processing.")
    doc = MedicalDocument.objects.select_for_update().select_related(
        "queue_entry__daily_queue"
    ).get(id=medical_document_id)
    latest_version = (
        MedicalDocumentVersion.objects.select_for_update()
        .filter(medical_document_id=medical_document_id)
        .order_by("-version_no")
        .prefetch_related(
            Prefetch("outbox_events", queryset=OutboxEvent.objects.order_by("-created_at"))
        )
        .first()
    )
    if latest_version is None:
        raise DomainError("No document version found.")
    retryable = _latest_retryable_event(latest_version)
    if retryable is None:
        raise DomainError("No retryable processing step found for latest version.")
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
            **_assigned_doctor_metadata(doc),
        },
    )
    return retried
