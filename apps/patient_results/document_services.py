"""Services for patient results document list and PDF download."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from django.conf import settings

from apps.medical.models import DocVersionStatus, MedicalDocumentVersion, PdfStatus


def list_patient_documents(patient_id: UUID) -> list[dict]:
    """
    List published medical document versions for a patient.
    Returns version_id, queue_date, document_id. Only current versions, no retention, no revoked.
    """
    versions = (
        MedicalDocumentVersion.objects.filter(
            medical_document__queue_entry__patient_id=patient_id,
            version_status=DocVersionStatus.PUBLISHED,
            pdf_generation_status=PdfStatus.COMPLETED,
            local_pdf_deleted_at__isnull=True,
            revoked_at__isnull=True,
        )
        .select_related("medical_document", "medical_document__queue_entry", "medical_document__queue_entry__daily_queue")
        .order_by("-published_at")
    )
    result: list[dict] = []
    for v in versions:
        doc = v.medical_document
        if v.version_no != doc.current_version_no:
            continue
        queue_date = doc.queue_entry.daily_queue.queue_date
        result.append(
            {
                "version_id": str(v.id),
                "document_id": str(doc.id),
                "queue_date": queue_date.isoformat(),
                "published_at": v.published_at.isoformat() if v.published_at else None,
            }
        )
    return result


def get_patient_pdf_version(version_id: UUID, patient_id: UUID) -> MedicalDocumentVersion | None:
    """Get version if it belongs to the patient and is available for download."""
    try:
        return (
            MedicalDocumentVersion.objects.select_related(
                "medical_document",
                "medical_document__queue_entry",
                "medical_document__queue_entry__daily_queue",
            )
            .get(
                id=version_id,
                medical_document__queue_entry__patient_id=patient_id,
                version_status=DocVersionStatus.PUBLISHED,
                pdf_generation_status=PdfStatus.COMPLETED,
                local_pdf_deleted_at__isnull=True,
                revoked_at__isnull=True,
            )
        )
    except MedicalDocumentVersion.DoesNotExist:
        return None


def get_patient_pdf_path(
    version_id: UUID, patient_id: UUID, version: MedicalDocumentVersion | None = None
) -> Path | None:
    """
    Resolve PDF path for a version if it belongs to the patient and is available.
    Returns Path or None if not found/not accessible.
    Pass version to avoid duplicate DB query when already fetched.
    """
    if version is None:
        version = get_patient_pdf_version(version_id, patient_id)
    if not version or not version.pdf_local_path:
        return None
    path = Path(version.pdf_local_path)
    if not path.is_absolute():
        path = Path(settings.MEDIA_ROOT) / path
    if not path.exists() or not path.is_file():
        return None
    # Path traversal guard
    media_resolved = Path(settings.MEDIA_ROOT).resolve()
    if not path.resolve().is_relative_to(media_resolved):
        return None
    return path


