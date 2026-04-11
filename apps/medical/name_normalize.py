"""Normalize patient names and PDF stems for HiDrive /incoming matching (RODO-safe)."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reception.models import Patient


def normalize_name(name: str) -> str:
    """Normalize a name or filename stem: NFKD, strip diacritics, lowercase, `_` separator."""
    raw = (name or "").replace("ß", "ss").replace("ẞ", "SS")
    nfkd = unicodedata.normalize("NFKD", raw)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_only.strip().replace("-", "_").replace(" ", "_").lower()


def _stem_without_pdf(filename_stem: str) -> str:
    s = (filename_stem or "").strip()
    low = s.lower()
    if low.endswith(".pdf"):
        return s[: -len(".pdf")].strip()
    return s


def build_patient_filename_candidates(patient: Patient) -> list[str]:
    """Return four normalized filename stems (no ``.pdf``) for the patient."""
    first = normalize_name(patient.first_name)
    last = normalize_name(patient.last_name)
    candidates = [f"{first}_{last}", f"{last}_{first}"]
    if patient.date_of_birth:
        dob_us = patient.date_of_birth.isoformat().replace("-", "_")
        candidates += [f"{first}_{last}_{dob_us}", f"{last}_{first}_{dob_us}"]
    return candidates


def match_filename_to_candidates(filename_stem: str, candidates: list[str]) -> bool:
    """Strict match: exact stem or stem equal to candidate + ``_`` + digits (multi-file)."""
    norm = normalize_name(_stem_without_pdf(filename_stem))
    for c in candidates:
        if norm == c:
            return True
        if re.fullmatch(re.escape(c) + r"_\d+", norm):
            return True
    return False


def dated_match_candidates(patient: Patient) -> list[str]:
    """Normalized stems that include date of birth (may be empty if no DOB)."""
    if not patient.date_of_birth:
        return []
    first = normalize_name(patient.first_name)
    last = normalize_name(patient.last_name)
    dob_us = patient.date_of_birth.isoformat().replace("-", "_")
    return [f"{first}_{last}_{dob_us}", f"{last}_{first}_{dob_us}"]


def stem_matches_dated_variant(filename_stem: str, patient: Patient) -> bool:
    """True if stem matches one of the DOB-inclusive filename variants."""
    dated = dated_match_candidates(patient)
    if not dated:
        return False
    return match_filename_to_candidates(filename_stem, dated)
