from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from django.db import transaction
from django.db.models import Max, Prefetch, Q
from django.utils import timezone

from apps.core.exceptions import DomainError, IdempotencyConflictError, StateTransitionError
from apps.intake.models import IntakeStatus, PatientIntakeForm
from apps.intake.services import get_intake_form_context
from apps.medical.models import DocVersionStatus, MedicalDocStatus, MedicalDocument, MedicalDocumentVersion, PdfStatus
from apps.operations.services import create_audit_event
from apps.outbox.models import OutboxEvent, OutboxEventType, OutboxStatus
from apps.reception.models import QueueEntry


def create_or_get_medical_document(
    *,
    queue_entry_id: uuid.UUID,
    intake_form_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
) -> MedicalDocument:
    """Create medical document for queue entry if not existing."""
    QueueEntry.objects.get(id=queue_entry_id)
    intake_form = PatientIntakeForm.objects.get(id=intake_form_id)
    if intake_form.queue_entry_id != queue_entry_id:
        raise DomainError("Intake form does not belong to this queue entry.")
    medical_document, _ = MedicalDocument.objects.get_or_create(
        queue_entry_id=queue_entry_id,
        defaults={
            "intake_form_id": intake_form_id,
            "created_by_user_id": created_by_user_id,
            "updated_by_user_id": created_by_user_id,
        },
    )
    return medical_document


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
            metadata={
                "medical_document_version_id": str(latest_version.id),
                "version_no": latest_version.version_no,
                "mode": "update",
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
        metadata={
            "medical_document_version_id": str(created_version.id),
            "version_no": created_version.version_no,
            "mode": "create",
        },
    )
    return created_version


@transaction.atomic
def publish_document_version(
    *,
    medical_document_id: uuid.UUID,
    publish_request_id: uuid.UUID,
    published_by_user_id: uuid.UUID,
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
        raise StateTransitionError("No draft version available for publication.")

    draft_version.version_status = DocVersionStatus.PUBLISHED
    draft_version.publish_request_id = publish_request_id
    draft_version.publish_requested_by_user_id = published_by_user_id
    draft_version.published_by_user_id = published_by_user_id
    draft_version.published_at = requested_at
    draft_version.pdf_generation_status = PdfStatus.PENDING
    draft_version.save(
        update_fields=[
            "version_status",
            "publish_request_id",
            "publish_requested_by_user",
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
        metadata={
            "medical_document_version_id": str(draft_version.id),
            "version_no": draft_version.version_no,
            "publish_request_id": str(publish_request_id),
        },
    )
    return draft_version


def list_medical_documents(
    *,
    status: str | None = None,
    queue_date: date | None = None,
    patient_search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[MedicalDocument], int]:
    """
    List medical documents for doctor work queue.
    Returns (list of documents with prefetched latest version, total count).
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
                queryset=MedicalDocumentVersion.objects.order_by("-version_no"),
            )
        )
        .order_by("-updated_at")
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
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """
    List doctor work queue: queue entries with submitted intake (ankieta pacjenta).
    Each item may or may not have an existing MedicalDocument.
    Returns (list of item dicts, total count). Item dict: document_id (or None), queue_entry_id,
    intake_form_id, patient, queue_date, status, pdf_generation_status, hidrive_sent, sms_sent.
    """
    qs = (
        PatientIntakeForm.objects.filter(form_status=IntakeStatus.SUBMITTED)
        .select_related("queue_entry", "queue_entry__patient", "queue_entry__daily_queue")
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
                queryset=MedicalDocumentVersion.objects.order_by("-version_no"),
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
        })
    return list_items, total


def get_medical_document_context(
    *,
    medical_document_id: uuid.UUID,
    form_locale: str = "de-DE",
) -> dict[str, Any]:
    """
    Build full context for doctor view: document, intake summary, current (latest) version.
    Raises ObjectDoesNotExist if document not found.
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
                queryset=MedicalDocumentVersion.objects.order_by("-version_no"),
            )
        )
        .get(id=medical_document_id)
    )
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
