"""HiDrive /incoming PDF matching, gate, download, and reject (no local disk cache)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings
from django.db.models import Q

from pypdf import PdfReader

from apps.integrations.hidrive.client import get_hidrive_adapter
from apps.medical.models import (
    ExternalPdfAttachment,
    ExternalPdfStatus,
    MedicalDocument,
)
from apps.medical.name_normalize import (
    _stem_without_pdf,
    build_patient_filename_candidates,
    incoming_stem_norm_lookup_bases,
    match_filename_to_candidates,
    normalize_name,
    stem_matches_dated_variant,
)
from apps.reception.models import Patient

logger = logging.getLogger(__name__)


class ExternalPdfCorruptError(Exception):
    """Downloaded bytes are not a valid complete PDF."""


@dataclass(frozen=True)
class MatchedIncomingFile:
    """One PDF under ``/incoming`` matched to the current patient."""

    name: str
    path: str


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


def hidrive_incoming_dir() -> str:
    raw = (
        getattr(settings, "HIDRIVE_INCOMING_PATH", "/incoming") or "/incoming"
    ).strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or "/incoming"


def hidrive_processed_dir() -> str:
    raw = (
        getattr(settings, "HIDRIVE_PROCESSED_PATH", "/processed") or "/processed"
    ).strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or "/processed"


def _pdf_basename_from_listing_entry(entry: dict[str, Any]) -> str | None:
    """HiDrive /dir sometimes puts the full filename only in ``path``; ``name`` may omit ``.pdf``."""
    path = str(entry.get("path") or "").strip()
    name = str(entry.get("name") or "").strip()
    for candidate in (path, name):
        if not candidate:
            continue
        base = PurePosixPath(candidate.replace("\\", "/")).name
        if base.lower().endswith(".pdf"):
            return base
    return None


def _ambiguous_undated_stem(stem: str) -> bool:
    """More than one patient matches this stem without using a DOB-specific filename."""
    norm = normalize_name(_stem_without_pdf(stem))
    bases = incoming_stem_norm_lookup_bases(norm)
    qs = Patient.objects.filter(
        Q(incoming_pdf_name_key_fl__in=bases) | Q(incoming_pdf_name_key_lf__in=bases)
    ).only("id", "first_name", "last_name", "date_of_birth")
    count = 0
    for p in qs:
        candidates = build_patient_filename_candidates(p)
        if not match_filename_to_candidates(stem, candidates):
            continue
        if stem_matches_dated_variant(stem, p):
            continue
        count += 1
        if count > 1:
            return True
    return False


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
    adapter = get_hidrive_adapter()
    inc = hidrive_incoming_dir()
    try:
        entries = adapter.list_dir(remote_path=inc)
    except Exception:
        logger.exception("HiDrive list_dir failed for gate")
        # Do not block the doctor UI on HiDrive outages; optional /incoming PDFs.
        return GateResult(True, (), error_hidrive, skip_attachment_sync=True)

    logger.info(
        "external_pdf_gate: incoming directory readable path=%s raw_entry_count=%s",
        inc,
        len(entries),
    )

    pdf_rows: list[tuple[dict[str, Any], str]] = []
    for entry in entries:
        pdf_name = _pdf_basename_from_listing_entry(entry)
        if not pdf_name:
            continue
        pdf_rows.append((entry, pdf_name))

    if not pdf_rows:
        logger.info(
            "external_pdf_gate: no PDF-like files under %s after listing (folder OK)",
            inc,
        )
        return GateResult(False, (), error_no_pdfs_in_folder)

    matched: list[MatchedIncomingFile] = []
    skipped_ambiguous = False
    for _entry, pdf_name in pdf_rows:
        if pdf_name.lower().startswith("rejected_"):
            continue
        stem = PurePosixPath(pdf_name).stem
        patient_candidates = build_patient_filename_candidates(patient)
        if not match_filename_to_candidates(stem, patient_candidates):
            continue
        if not stem_matches_dated_variant(stem, patient):
            if _ambiguous_undated_stem(stem):
                skipped_ambiguous = True
                continue
        logical_path = f"{inc}/{pdf_name}".replace("//", "/")
        matched.append(MatchedIncomingFile(name=pdf_name, path=logical_path))

    if not matched:
        msg = error_ambiguous if skipped_ambiguous else error_no_file
        return GateResult(False, (), msg)
    return GateResult(True, tuple(matched), None)


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
    """Map incoming logical paths to the processed archive path.

    Laboratory PDFs are always under ``HIDRIVE_INCOMING_PATH`` (default ``/incoming/``).

    - Paths under that prefix → same relative path under ``HIDRIVE_PROCESSED_PATH``.
    - Any other path (should not occur for matched attachments) → basename only
      under ``HIDRIVE_PROCESSED_PATH``.
    """
    inc = hidrive_incoming_dir()
    proc = hidrive_processed_dir()
    norm = (incoming_path or "").strip().replace("\\", "/")
    if not norm.startswith("/"):
        norm = "/" + norm
    if norm.startswith(inc + "/"):
        suffix = norm[len(inc) :].lstrip("/")
        return f"{proc}/{suffix}".replace("//", "/")
    return f"{proc}/{PurePosixPath(norm).name}".replace("//", "/")
