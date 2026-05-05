"""
Medical app constants: admin/API choices, document locking, paper-intake policy knobs.

Lesion preset choices: codes from ``medical_payload_schemas``, labels from ``befund_text`` (EN).
"""

from __future__ import annotations

from typing import get_args

from apps.medical.befund_text import (
    CLINICAL_ASSESSMENT_LABELS,
    DERMATOSCOPIC_LABELS,
    MALIGNANCY_RISK_LABELS,
)
from apps.medical.medical_payload_schemas import (
    ClinicalAssessmentCode,
    DermatoscopicFeatureCode,
    MalignancyRiskCode,
)

# Choices as (value, label) for admin widgets; EN label at index 1
DERMATOSCOPIC_FEATURE_CHOICES: list[tuple[str, str]] = [
    (code, DERMATOSCOPIC_LABELS.get(code, (code, code))[1])
    for code in get_args(DermatoscopicFeatureCode)
]

CLINICAL_ASSESSMENT_CHOICES: list[tuple[str, str]] = [
    (code, CLINICAL_ASSESSMENT_LABELS.get(code, (code, code))[1])
    for code in get_args(ClinicalAssessmentCode)
]

MALIGNANCY_RISK_CHOICES: list[tuple[str, str]] = [
    (code, MALIGNANCY_RISK_LABELS.get(code, (code, code))[1])
    for code in get_args(MalignancyRiskCode)
]

DOCUMENT_LOCK_TIMEOUT_HOURS = 6
DOCTOR_LIST_UNPUBLISHED_SLA_HOURS = 24
PAPER_INTAKE_MIN_HOURS_AFTER_APPOINTMENT = 3
PAPER_INTAKE_HUB_QUEUE_ENTRY_LOOKBACK_DAYS = 30
PAPER_INTAKE_AUTH_REASON_MIN_LEN = 10
PAPER_INTAKE_AUTH_REASON_MAX_LEN = 500
