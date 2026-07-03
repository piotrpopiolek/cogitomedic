"""HiDrive /incoming PDF matching, gate, download, and reject (no local disk cache)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

from django.conf import settings
from pypdf import PdfReader

from apps.integrations.hidrive.client import get_hidrive_adapter
from apps.medical.incoming_pdf_scan import (
    IncomingMatchStatus,
    MatchedIncomingFile,
    _ambiguous_undated_stem,
    _full_incoming_pdf_path,
    _is_reception_external_upload_incoming_path,
    _normalize_incoming_logical_path,
    _pdf_basename_from_listing_entry,
    evaluate_patient_incoming_match,
    hidrive_incoming_dir,
    list_incoming_lab_pdf_rows,
)
from apps.medical.models import (
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocument,
)
from apps.reception.models import Patient

logger = logging.getLogger(__name__)

__all__ = [
    "ExternalPdfCorruptError",
    "GateResult",
    "MatchedIncomingFile",
    "_ambiguous_undated_stem",
    "_full_incoming_pdf_path",
    "_is_reception_external_upload_incoming_path",
    "_normalize_incoming_logical_path",
    "_pdf_basename_from_listing_entry",
    "check_external_pdf_gate",
    "create_attachment_records",
    "download_external_pdf",
    "hidrive_incoming_dir",
    "hidrive_processed_dir",
    "logical_path_to_processed",
    "reject_external_pdf",
]


class ExternalPdfCorruptError(Exception):
    """Downloaded bytes are not a valid complete PDF."""


@dataclass(frozen=True)
class GateResult:
    passed: bool
    matched_files: tuple[MatchedIncomingFile, ...]
    #: When ``passed`` is False, gate failure reason. When ``passed`` is True with
    #: ``skip_attachment_sync`` (HiDrive listing failed), a soft warning for the UI.
    error_message: str | None
    #: When True, HiDrive listing failed — caller must not sync DB attachments from
    #: ``matched_files`` (would clear stale MATCHED rows while cloud is unreachable).
    skip_attachment_sync: bool = False


def hidrive_processed_dir() -> str:
    raw = (
        getattr(settings, "HIDRIVE_PROCESSED_PATH", "/processed") or "/processed"
    ).strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or "/processed"


def check_external_pdf_gate(
    patient: Patient,
    *,
    error_no_file: str,
    error_no_pdfs_in_folder: str,
    error_ambiguous: str,
    error_hidrive: str,
) -> GateResult:
    """
    Two-phase gate: (1) list ``/incoming`` — if that fails, HiDrive is unreadable;
    (2) among PDF-like filenames, match to the patient (strict + diacritics), no download.
    """
    listing = list_incoming_lab_pdf_rows()
    if not listing.hidrive_ok:
        return GateResult(True, (), error_hidrive, skip_attachment_sync=True)

    logger.info(
        "external_pdf_gate: incoming directory readable path=%s raw_pdf_count=%s",
        listing.incoming_path,
        len(listing.pdf_rows),
    )

    if listing.folder_empty:
        logger.info(
            "external_pdf_gate: no PDF-like files under %s after listing (folder OK)",
            listing.incoming_path,
        )
        return GateResult(False, (), error_no_pdfs_in_folder)

    match = evaluate_patient_incoming_match(
        patient,
        listing.pdf_rows,
        incoming_dir=listing.incoming_path,
    )
    if match.status == IncomingMatchStatus.MATCHED:
        return GateResult(True, match.matched_files, None)
    if match.status == IncomingMatchStatus.AMBIGUOUS:
        return GateResult(False, (), error_ambiguous)
    return GateResult(False, (), error_no_file)


def create_attachment_records(
    medical_document: MedicalDocument,
    matched_files: tuple[MatchedIncomingFile, ...],
) -> list[ExternalPdfAttachment]:
    """Create or refresh MATCHED ``ExternalPdfAttachment`` rows (idempotent by path)."""
    paths = {m.path for m in matched_files}
    ExternalPdfAttachment.objects.filter(
        medical_document=medical_document,
        status=ExternalPdfStatus.MATCHED,
    ).exclude(hidrive_remote_path__in=paths).delete()

    out: list[ExternalPdfAttachment] = []
    for m in matched_files:
        att, _created = ExternalPdfAttachment.objects.update_or_create(
            medical_document=medical_document,
            hidrive_remote_path=m.path,
            defaults={
                "original_filename": m.name,
                "status": ExternalPdfStatus.MATCHED,
            },
        )
        out.append(att)
    return out


def download_external_pdf(attachment: ExternalPdfAttachment) -> bytes:
    """Download PDF from HiDrive and validate with ``PdfReader``."""
    adapter = get_hidrive_adapter()
    data = adapter.download(remote_path=attachment.hidrive_remote_path)
    try:
        reader = PdfReader(BytesIO(data))
        if len(reader.pages) < 1:
            raise ValueError("PDF has no pages")
    except Exception as exc:
        raise ExternalPdfCorruptError("invalid or incomplete PDF") from exc
    return data


def reject_external_pdf(attachment: ExternalPdfAttachment) -> None:
    """Rename on HiDrive to ``rejected_<name>`` and mark attachment REJECTED."""
    if attachment.status == ExternalPdfStatus.REJECTED:
        return
    src = attachment.hidrive_remote_path
    src_pp = PurePosixPath((src or "").strip().replace("\\", "/"))
    parent = str(src_pp.parent) or "/"
    base_name = src_pp.name
    if base_name.lower().startswith("rejected_"):
        attachment.status = ExternalPdfStatus.REJECTED
        attachment.save(update_fields=["status"])
        return
    dest = f"{parent.rstrip('/')}/rejected_{base_name}".replace("//", "/")
    adapter = get_hidrive_adapter()
    adapter.move_file(source_path=src, dest_path=dest)
    attachment.hidrive_remote_path = dest
    attachment.original_filename = f"rejected_{base_name}"
    attachment.status = ExternalPdfStatus.REJECTED
    attachment.save(
        update_fields=[
            "hidrive_remote_path",
            "original_filename",
            "status",
        ]
    )


def logical_path_to_processed(incoming_path: str) -> str:
    """Map incoming logical paths to the processed archive path."""
    inc = hidrive_incoming_dir()
    proc = hidrive_processed_dir()
    norm = (incoming_path or "").strip().replace("\\", "/")
    if not norm.startswith("/"):
        norm = "/" + norm
    if norm.startswith(inc + "/"):
        suffix = norm[len(inc) :].lstrip("/")
        return f"{proc}/{suffix}".replace("//", "/")
    return f"{proc}/{PurePosixPath(norm).name}".replace("//", "/")
