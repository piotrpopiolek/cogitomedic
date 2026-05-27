"""Shared patient identity normalization and lookup (reception + import)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from uuid import UUID

from django.db.models import Q

from apps.core.domain_messages import domain_message
from apps.core.exceptions import DomainError
from apps.reception.models import Patient
from apps.reception.phone_utils import (
    normalize_phone_for_patient_storage,
    phone_lookup_variants,
)

_PLACEHOLDER_NAMES = frozenset({"—", "-"})


def normalize_patient_name(value: str) -> str:
    """Trim and collapse whitespace; preserve casing as stored in DB."""
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_patient_name_for_storage(value: str) -> str:
    """
    Title-case person name (same rules as XLSX import) before persisting.
    """
    value = normalize_patient_name(value)
    if not value:
        return ""
    chunks = re.split(r"([\-'\s])", value.lower())
    normalized_chunks = [
        (
            chunk[:1].upper() + chunk[1:]
            if chunk and not re.fullmatch(r"[\-'\s]", chunk)
            else chunk
        )
        for chunk in chunks
    ]
    return "".join(normalized_chunks)


def normalize_patient_phone_for_storage(phone: str) -> str:
    return normalize_phone_for_patient_storage(phone)


def patient_identity_key(
    *,
    first_name: str,
    last_name: str,
    phone: str,
    date_of_birth: date,
) -> tuple[str, str, str, date]:
    return (
        normalize_patient_name_for_storage(first_name),
        normalize_patient_name_for_storage(last_name),
        normalize_patient_phone_for_storage(phone),
        date_of_birth,
    )


def validate_patient_names_for_import(*, first_name: str, last_name: str) -> None:
    first = normalize_patient_name(first_name)
    last = normalize_patient_name(last_name)
    if (
        not first
        or not last
        or first in _PLACEHOLDER_NAMES
        or last in _PLACEHOLDER_NAMES
    ):
        raise DomainError(
            domain_message("other.domain.import_missing_patient_name"),
            api_message_key="other.domain.import_missing_patient_name",
        )


def patient_is_import_anonymized(patient: Patient) -> bool:
    if getattr(patient, "anonymized_at", None) is not None:
        return True
    return (patient.first_name or "").strip().upper() == "ANONYMIZED"


def patient_is_active_record(patient: Patient) -> bool:
    """Eligible for portal OTP, shared-phone cohort, and import identity match."""
    if patient_is_import_anonymized(patient):
        return False
    return bool(patient.is_active)


def find_patient_for_import(
    *,
    first_name: str,
    last_name: str,
    phone: str,
    date_of_birth: date,
) -> Patient | None:
    """Active patient matching the full identity tuple, or None."""
    key = patient_identity_key(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        date_of_birth=date_of_birth,
    )
    try:
        patient = Patient.objects.get(
            first_name=key[0],
            last_name=key[1],
            phone=key[2],
            date_of_birth=key[3],
        )
    except Patient.DoesNotExist:
        return None
    if not patient_is_active_record(patient):
        return None
    return patient


def _iter_patients_matching_phone(
    phone: str,
    *,
    extra_q: Q | None = None,
) -> list[Patient]:
    """
    Patients whose stored ``phone`` matches any lookup variant of ``phone``.

    Uses the same variant set as the patient-results portal. After DB backfill
    (``normalize_patient_phone_for_storage`` on every row) rows should match the
    canonical variant; variants still cover legacy rows and pre-save API input.
    """
    by_id: dict[UUID, Patient] = {}
    extra = extra_q if extra_q is not None else Q()
    for variant in phone_lookup_variants(phone):
        for patient in Patient.objects.filter(
            _phone_match_q(variant),
        ).filter(extra):
            if patient.id in by_id:
                continue
            by_id[patient.id] = patient
    return sorted(by_id.values(), key=lambda p: p.created_at)


def stale_anonymized_patient_blocks_phone(*, phone: str) -> bool:
    """
    True when an anonymized row still holds this phone (legacy/test edge case).
    """
    return bool(
        _iter_patients_matching_phone(
            phone,
            extra_q=Q(anonymized_at__isnull=False),
        )
    )


def assert_phone_not_blocked_by_stale_anonymized(
    *,
    phone: str,
    exclude_patient_id=None,
) -> None:
    """
    Block assigning this phone when a stale anonymized row still holds it.

    Skips the check when ``exclude_patient_id`` already uses the normalized phone
    (manual update without changing phone).
    """
    if exclude_patient_id is not None and _iter_patients_matching_phone(
        phone,
        extra_q=Q(id=exclude_patient_id),
    ):
        return
    if stale_anonymized_patient_blocks_phone(phone=phone):
        raise DomainError(
            domain_message("other.domain.import_patient_anonymized_same_phone"),
            api_message_key="other.domain.import_patient_anonymized_same_phone",
        )


def assert_patient_identity_available(
    *,
    first_name: str,
    last_name: str,
    phone: str,
    date_of_birth: date,
    exclude_patient_id=None,
) -> None:
    key = patient_identity_key(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        date_of_birth=date_of_birth,
    )
    qs = Patient.objects.filter(
        first_name=key[0],
        last_name=key[1],
        phone=key[2],
        date_of_birth=key[3],
    )
    if exclude_patient_id is not None:
        qs = qs.exclude(id=exclude_patient_id)
    if qs.exists():
        raise DomainError(
            domain_message("other.domain.patient_identity_conflict"),
            api_message_key="other.domain.patient_identity_conflict",
        )


def _phone_match_q(phone_normalized: str) -> Q:
    if not phone_normalized:
        return Q(pk=None)
    return Q(phone=phone_normalized) | Q(phone=f"+{phone_normalized}")


def find_active_patients_by_phone(
    phone: str,
    *,
    exclude_patient_id: UUID | None = None,
) -> list[Patient]:
    """Active (``is_active``), non-anonymized patients matching ``phone``."""
    patients = _iter_patients_matching_phone(phone)
    active = [p for p in patients if patient_is_active_record(p)]
    if exclude_patient_id is not None:
        active = [p for p in active if p.id != exclude_patient_id]
    return active


def find_active_patients_by_phone_and_dob(
    phone: str,
    date_of_birth: date,
) -> list[Patient]:
    """Active, non-anonymized patients matching phone variants and date of birth."""
    return [
        patient
        for patient in find_active_patients_by_phone(phone)
        if patient.date_of_birth == date_of_birth
    ]


def resolve_patient_for_portal(
    phone: str,
    date_of_birth: date,
    last_name: str | None = None,
) -> Patient | None:
    """
    Resolve a single patient for portal OTP.

    Returns None when there is no match, or when multiple candidates exist and
    ``last_name`` is missing or does not disambiguate.
    """
    patients = find_active_patients_by_phone_and_dob(phone, date_of_birth)
    if not patients:
        return None
    if len(patients) == 1:
        return patients[0]
    normalized_last = normalize_patient_name_for_storage(last_name or "")
    if not normalized_last:
        return None
    matched = [
        patient
        for patient in patients
        if normalize_patient_name_for_storage(patient.last_name) == normalized_last
    ]
    return matched[0] if len(matched) == 1 else None


def portal_identity_is_ambiguous(
    phone: str,
    date_of_birth: date,
    last_name: str | None = None,
) -> bool:
    """True when more than one active patient matches phone+DOB without a unique last name."""
    patients = find_active_patients_by_phone_and_dob(phone, date_of_birth)
    if len(patients) <= 1:
        return False
    return resolve_patient_for_portal(phone, date_of_birth, last_name) is None


def other_active_patients_with_same_phone(
    *,
    phone: str,
    exclude_patient_id: UUID | None = None,
) -> list[Patient]:
    return find_active_patients_by_phone(
        phone,
        exclude_patient_id=exclude_patient_id,
    )


def build_shared_phone_warnings(
    *,
    phone: str,
    exclude_patient_id: UUID | None = None,
) -> list[dict[str, Any]]:
    others = other_active_patients_with_same_phone(
        phone=phone,
        exclude_patient_id=exclude_patient_id,
    )
    if not others:
        return []
    return [
        {
            "code": "shared_phone",
            "message_key": "other.api.patient_shared_phone_warning",
            "other_patients": [
                {
                    "id": str(patient.id),
                    "first_name": patient.first_name,
                    "last_name": patient.last_name,
                    "date_of_birth": (
                        patient.date_of_birth.isoformat()
                        if patient.date_of_birth
                        else None
                    ),
                }
                for patient in others
            ],
        }
    ]
