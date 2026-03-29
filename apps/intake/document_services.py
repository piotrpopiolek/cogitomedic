"""Read-only services for listing and accessing intake document versions (PDF) for RECEPTION/ADMIN."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.db.models import QuerySet

from apps.core.api_utils import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    get_scoped_clinic_site_ids,
    safe_parse_positive_int,
)
from apps.intake.models import IntakeDocumentVersion, IntakeOutboxEvent, IntakeOutboxStatus


def _latest_processing_error(version: IntakeDocumentVersion) -> str | None:
    """Return latest error_message from failed/dead_letter outbox events for this version."""
    failed = (
        IntakeOutboxEvent.objects.filter(
            intake_document_version_id=version.id,
            status__in=[IntakeOutboxStatus.FAILED, IntakeOutboxStatus.DEAD_LETTER],
        )
        .exclude(error_message="")
        .order_by("-updated_at")
        .values_list("error_message", flat=True)
        .first()
    )
    return failed


def parse_intake_documents_list_params(get_params: Any) -> dict[str, Any]:
    """Parse GET params for intake documents list. Returns queue_date, pdf_generation_status, patient_search, clinic_site_id, page, page_size."""
    queue_date = None
    if get_params.get("queue_date"):
        raw = get_params.get("queue_date", "") or ""
        try:
            queue_date = datetime.strptime(raw, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    pdf_generation_status = get_params.get("pdf_generation_status") or None
    patient_search = (get_params.get("patient_search") or "").strip() or None
    clinic_site_id = get_params.get("clinic_site_id") or None
    page = safe_parse_positive_int(get_params.get("page"), default=1, maximum=10_000)
    page_size = safe_parse_positive_int(
        get_params.get("page_size"),
        default=DEFAULT_LIST_LIMIT,
        maximum=MAX_LIST_LIMIT,
    )
    return {
        "queue_date": queue_date,
        "pdf_generation_status": pdf_generation_status,
        "patient_search": patient_search,
        "clinic_site_id": clinic_site_id,
        "page": page,
        "page_size": page_size,
    }


def _intake_documents_queryset() -> QuerySet[IntakeDocumentVersion]:
    return (
        IntakeDocumentVersion.objects.select_related(
            "intake_form",
            "intake_form__queue_entry",
            "intake_form__queue_entry__patient",
            "intake_form__queue_entry__daily_queue",
            "intake_form__queue_entry__daily_queue__clinic_site",
        )
        .order_by("-created_at")
    )


def list_intake_documents(
    *,
    user: Any,
    queue_date: date | None = None,
    pdf_generation_status: str | None = None,
    patient_search: str | None = None,
    clinic_site_id: UUID | None = None,
    page: int = 1,
    page_size: int = DEFAULT_LIST_LIMIT,
) -> tuple[list[IntakeDocumentVersion], int]:
    """
    List intake document versions for RECEPTION/ADMIN.
    RECEPTION sees only documents from their assigned clinic_sites; ADMIN sees all.
    """
    qs = _intake_documents_queryset()
    scope_ids = get_scoped_clinic_site_ids(user)
    if scope_ids is not None:
        if not scope_ids:
            return [], 0
        qs = qs.filter(
            intake_form__queue_entry__daily_queue__clinic_site_id__in=scope_ids
        )
    if queue_date is not None:
        qs = qs.filter(
            intake_form__queue_entry__daily_queue__queue_date=queue_date
        )
    if pdf_generation_status:
        qs = qs.filter(pdf_generation_status=pdf_generation_status)
    if clinic_site_id is not None:
        qs = qs.filter(
            intake_form__queue_entry__daily_queue__clinic_site_id=clinic_site_id
        )
    if patient_search:
        qs = qs.filter(
            Q(intake_form__queue_entry__patient__last_name__icontains=patient_search)
            | Q(
                intake_form__queue_entry__patient__first_name__icontains=patient_search
            )
        )
    qs = qs.filter(anonymization_deleted_at__isnull=True)
    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    return list(qs[start:end]), total


def check_intake_document_access(version: IntakeDocumentVersion, user: Any) -> None:
    """Raise ObjectDoesNotExist if user (RECEPTION/ADMIN) does not have access to this version."""
    if getattr(user, "is_admin_role", False) and user.is_admin_role:
        return
    scope_ids = get_scoped_clinic_site_ids(user)
    if scope_ids is None:
        return
    clinic_site_id = (
        version.intake_form.queue_entry.daily_queue.clinic_site_id
    )
    if clinic_site_id not in scope_ids:
        raise ObjectDoesNotExist("Intake document not found.")


def get_intake_document_detail(version: IntakeDocumentVersion) -> dict[str, Any]:
    """Build detail payload for one IntakeDocumentVersion (no snapshot payload in response)."""
    entry = version.intake_form.queue_entry
    queue = entry.daily_queue
    patient = entry.patient
    clinic_site = queue.clinic_site
    return {
        "id": str(version.id),
        "version_no": version.version_no,
        "form_locale": version.form_locale,
        "pdf_generation_status": version.pdf_generation_status,
        "pdf_local_path": version.pdf_local_path,
        "pdf_checksum_sha256": version.pdf_checksum_sha256,
        "hidrive_path": version.hidrive_path,
        "hidrive_sent": version.hidrive_sent,
        "hidrive_sent_at": (
            version.hidrive_sent_at.isoformat() if version.hidrive_sent_at else None
        ),
        "created_at": version.created_at.isoformat(),
        "pdf_available": (
            version.pdf_generation_status == "COMPLETED"
            and bool(version.pdf_local_path)
        ),
        "intake_form_id": str(version.intake_form_id),
        "queue_entry_id": str(entry.id),
        "queue_date": queue.queue_date.isoformat(),
        "clinic_site_id": str(clinic_site.id),
        "clinic_site_name": clinic_site.name or clinic_site.code,
        "patient": {
            "id": str(patient.id),
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        },
        "processing_error_message": _latest_processing_error(version),
    }


def get_intake_document_list_item(version: IntakeDocumentVersion) -> dict[str, Any]:
    """Serialize one version for list response."""
    entry = version.intake_form.queue_entry
    queue = entry.daily_queue
    patient = entry.patient
    clinic_site = queue.clinic_site
    return {
        "id": str(version.id),
        "version_no": version.version_no,
        "form_locale": version.form_locale,
        "pdf_generation_status": version.pdf_generation_status,
        "created_at": version.created_at.isoformat(),
        "queue_entry_id": str(entry.id),
        "intake_form_id": str(version.intake_form_id),
        "queue_date": queue.queue_date.isoformat(),
        "clinic_site_id": str(clinic_site.id),
        "clinic_site_name": clinic_site.name or clinic_site.code,
        "patient": {
            "id": str(patient.id),
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        },
        "pdf_available": (
            version.pdf_generation_status == "COMPLETED"
            and bool(version.pdf_local_path)
        ),
        "hidrive_sent": version.hidrive_sent,
        "processing_error_message": _latest_processing_error(version),
    }


def read_intake_pdf_bytes(version: IntakeDocumentVersion) -> bytes:
    """Read PDF file from MEDIA_ROOT + pdf_local_path. Raises FileNotFoundError if missing."""
    if not version.pdf_local_path:
        raise FileNotFoundError("No PDF path")
    path = Path(settings.MEDIA_ROOT) / version.pdf_local_path
    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")
    return path.read_bytes()
