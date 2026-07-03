"""Shared HiDrive /incoming PDF listing and patient filename matching."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings
from django.db.models import Q

from apps.integrations.hidrive.client import (
    HiDriveTimeoutError,
    get_hidrive_adapter,
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


def hidrive_incoming_dir() -> str:
    raw = (
        getattr(settings, "HIDRIVE_INCOMING_PATH", "/incoming") or "/incoming"
    ).strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or "/incoming"


class IncomingMatchStatus(str, Enum):
    MATCHED = "MATCHED"
    NO_FILE = "NO_FILE"
    AMBIGUOUS = "AMBIGUOUS"
    REJECTED_ONLY = "REJECTED_ONLY"
    FOLDER_EMPTY = "FOLDER_EMPTY"
    HIDRIVE_ERROR = "HIDRIVE_ERROR"
    OK = "OK"


@dataclass(frozen=True)
class MatchedIncomingFile:
    """One PDF under ``/incoming`` matched to the current patient."""

    name: str
    path: str


@dataclass(frozen=True)
class IncomingPdfListing:
    pdf_rows: list[tuple[dict[str, Any], str]]
    hidrive_ok: bool
    folder_empty: bool
    incoming_path: str


@dataclass(frozen=True)
class PatientIncomingMatchResult:
    status: IncomingMatchStatus
    matched_files: tuple[MatchedIncomingFile, ...] = ()
    rejected_filenames: tuple[str, ...] = ()


def _pdf_basename_from_listing_entry(entry: dict[str, Any]) -> str | None:
    path = str(entry.get("path") or "").strip()
    name = str(entry.get("name") or "").strip()
    for candidate in (path, name):
        if not candidate:
            continue
        base = PurePosixPath(candidate.replace("\\", "/")).name
        if base.lower().endswith(".pdf"):
            return base
    return None


def _normalize_incoming_logical_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p:
        return ""
    return p if p.startswith("/") else f"/{p}"


def _full_incoming_pdf_path(entry: dict[str, Any], inc: str, pdf_name: str) -> str:
    path = str(entry.get("path") or "").strip().replace("\\", "/")
    if path:
        return _normalize_incoming_logical_path(path)
    inc_root = _normalize_incoming_logical_path(inc).rstrip("/") or "/incoming"
    return _normalize_incoming_logical_path(f"{inc_root}/{pdf_name}")


def _is_reception_external_upload_incoming_path(full_path: str, inc: str) -> bool:
    p = _normalize_incoming_logical_path(full_path)
    inc_n = _normalize_incoming_logical_path(inc).rstrip("/")
    if not p or not inc_n:
        return False
    prefix = f"{inc_n}/external-upload"
    return p == prefix or p.startswith(f"{prefix}/")


def _ambiguous_undated_stem(stem: str) -> bool:
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


def _display_filename_part(name: str) -> str:
    return "_".join(part for part in (name or "").split() if part)


def suggest_incoming_pdf_filename(patient: Patient) -> str:
    """Human-readable PDF name for reception (prefer DOB when undated stem is ambiguous)."""
    first = _display_filename_part(patient.first_name)
    last = _display_filename_part(patient.last_name)
    undated = f"{last}_{first}"
    use_dob = bool(patient.date_of_birth) and _ambiguous_undated_stem(undated)
    if use_dob and patient.date_of_birth:
        dob = patient.date_of_birth.isoformat().replace("-", "_")
        return f"{last}_{first}_{dob}.pdf"
    return f"{last}_{first}.pdf"


def list_incoming_lab_pdf_rows(
    *,
    hidrive_total_timeout_seconds: float | None = None,
) -> IncomingPdfListing:
    adapter = get_hidrive_adapter()
    inc = hidrive_incoming_dir()
    try:
        entries = adapter.list_dir(
            remote_path=inc,
            total_timeout_seconds=hidrive_total_timeout_seconds,
        )
    except HiDriveTimeoutError:
        logger.warning(
            "HiDrive list_dir timed out for incoming scan path=%s",
            inc,
        )
        raise
    except Exception:
        logger.exception("HiDrive list_dir failed for incoming scan")
        return IncomingPdfListing(
            pdf_rows=[],
            hidrive_ok=False,
            folder_empty=False,
            incoming_path=inc,
        )

    pdf_rows: list[tuple[dict[str, Any], str]] = []
    for entry in entries:
        pdf_name = _pdf_basename_from_listing_entry(entry)
        if not pdf_name:
            continue
        full_path = _full_incoming_pdf_path(entry, inc, pdf_name)
        if _is_reception_external_upload_incoming_path(full_path, inc):
            continue
        pdf_rows.append((entry, pdf_name))

    return IncomingPdfListing(
        pdf_rows=pdf_rows,
        hidrive_ok=True,
        folder_empty=not pdf_rows,
        incoming_path=inc,
    )


def evaluate_patient_incoming_match(
    patient: Patient,
    pdf_rows: list[tuple[dict[str, Any], str]],
    *,
    incoming_dir: str | None = None,
) -> PatientIncomingMatchResult:
    inc = incoming_dir or hidrive_incoming_dir()
    matched: list[MatchedIncomingFile] = []
    rejected_matches: list[str] = []
    skipped_ambiguous = False
    patient_candidates = build_patient_filename_candidates(patient)

    for entry, pdf_name in pdf_rows:
        if pdf_name.lower().startswith("rejected_"):
            bare_name = pdf_name[len("rejected_") :]
            bare_stem = PurePosixPath(bare_name).stem
            if match_filename_to_candidates(bare_stem, patient_candidates):
                if not stem_matches_dated_variant(bare_stem, patient):
                    if _ambiguous_undated_stem(bare_stem):
                        continue
                rejected_matches.append(pdf_name)
            continue

        stem = PurePosixPath(pdf_name).stem
        if not match_filename_to_candidates(stem, patient_candidates):
            continue
        if not stem_matches_dated_variant(stem, patient):
            if _ambiguous_undated_stem(stem):
                skipped_ambiguous = True
                continue
        logical_path = _full_incoming_pdf_path(entry, inc, pdf_name)
        matched.append(MatchedIncomingFile(name=pdf_name, path=logical_path))

    if matched:
        return PatientIncomingMatchResult(
            status=IncomingMatchStatus.MATCHED,
            matched_files=tuple(matched),
        )
    if rejected_matches:
        return PatientIncomingMatchResult(
            status=IncomingMatchStatus.REJECTED_ONLY,
            rejected_filenames=tuple(rejected_matches),
        )
    if skipped_ambiguous:
        return PatientIncomingMatchResult(status=IncomingMatchStatus.AMBIGUOUS)
    return PatientIncomingMatchResult(status=IncomingMatchStatus.NO_FILE)
