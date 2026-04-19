"""Normalize patient names and PDF stems for HiDrive /incoming matching (RODO-safe)."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reception.models import Patient


def normalize_name(name: str) -> str:
    """Normalize a name or filename stem: NFKD, strip diacritics, lowercase, `_` separator."""
    raw = (name or "").replace("ß", "ss").replace("ẞ", "SS")
    raw = " ".join(raw.split())
    nfkd = unicodedata.normalize("NFKD", raw)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_only = ascii_only.replace("ł", "l").replace("Ł", "L")
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


def _suffix_after_candidate_is_lab_or_multifile(norm: str, c: str) -> bool:
    """True if ``norm`` is ``c`` + ``_`` + suffix allowed for multi-file or lab exports.

    Rejects arbitrary extra tokens (e.g. ``…_wyniki_brata``) while allowing stems like
    ``last_first_CMBER2026FR08_20260417103840`` (timestamp tail or alphanumeric lab code).
    """
    if not norm.startswith(c + "_"):
        return False
    suffix = norm[len(c) + 1 :]
    if re.fullmatch(r"\d+", suffix):
        return True
    if re.search(r"_\d{12,}$", norm):
        return True
    first = suffix.split("_", 1)[0]
    return (
        len(first) >= 4
        and any(ch.isdigit() for ch in first)
        and any(ch.isalpha() for ch in first)
    )


def match_filename_to_candidates(filename_stem: str, candidates: list[str]) -> bool:
    """Match stem to candidates: exact, ``candidate_<n>`` multi-file, or lab-style suffix."""
    norm = normalize_name(_stem_without_pdf(filename_stem))
    for c in candidates:
        if norm == c:
            return True
        if re.fullmatch(re.escape(c) + r"_\d+", norm):
            return True
        if _suffix_after_candidate_is_lab_or_multifile(norm, c):
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


def compute_incoming_pdf_name_keys(first_name: str, last_name: str) -> tuple[str, str]:
    """Normalized ``first_last`` / ``last_first`` stems used for HiDrive /incoming lookup."""
    nf = normalize_name(first_name)
    nl = normalize_name(last_name)
    return f"{nf}_{nl}", f"{nl}_{nf}"


_INCOMING_STEM_DOB_TAIL = re.compile(r"_\d{4}_\d{2}_\d{2}$")


@lru_cache(maxsize=512)
def incoming_stem_norm_lookup_bases(norm: str) -> frozenset[str]:
    """Return DB lookup keys for an incoming filename stem (normalized, no ``.pdf``).

    Used with denormalized :class:`~apps.reception.models.Patient` fields so ambiguity
    checks need not scan the whole patient table. Includes a stripped ``_digits`` suffix
    for multi-file undated names (``Name_2``) but not when the tail looks like a DOB
    segment (``…_YYYY_MM_DD``). Long lab-style stems (``…_CMBER…_timestamp``) also add
    leading segment prefixes so ``first_last`` / ``last_first`` keys match.
    """
    bases: set[str] = {norm}
    if _INCOMING_STEM_DOB_TAIL.search(norm):
        return frozenset(bases)
    m = re.fullmatch(r"(.+)_(\d+)$", norm)
    if m:
        bases.add(m.group(1))
    segments = norm.split("_")
    if len(segments) >= 3:
        for k in range(2, len(segments)):
            bases.add("_".join(segments[:k]))
    return frozenset(bases)
