"""
Constants for lesion group preset choices used in admin and API.
Single source of truth: codes from medical_payload_schemas, labels from befund_text (EN).
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
