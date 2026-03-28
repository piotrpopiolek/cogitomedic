"""
Full Pydantic schema for medical_payload v1 (Befund). db-plan §5.2, api-plan §4.4.
Used for PUT draft validation.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --- Enum literals (Befund v1) ---

ExaminationScopeCode = Literal["INTIMATE_AREA_NOT_EXAMINED", "ORAL_MUCOSA_NOT_EXAMINED"]
FitzpatrickTypeCode = Literal[
    "TYPE_I", "TYPE_II", "TYPE_III", "TYPE_IV", "TYPE_V", "TYPE_VI",
    "TYPE_II_III", "UNDETERMINED",
]
OverallImageAssessmentCode = Literal["NO_CONTROL_NEEDED", "CONTROL_NEEDED"]
DermatoscopicFeatureCode = Literal[
    "ASYMMETRY", "IRREGULAR_BORDER", "INHOMOGENEOUS_PIGMENTATION", "MULTICOLOR",
    "ATYPICAL_PIGMENT_NETWORK", "IRREGULAR_GLOBULES", "IRREGULAR_DOTS",
    "STRUCTURELESS_AREAS", "ATYPICAL_VASCULAR_STRUCTURES", "REGRESSION_AREAS",
]
ClinicalAssessmentCode = Literal["UNREMARKABLE", "SLIGHTLY_ATYPICAL", "CONTROL_NEEDED", "SUSPICIOUS"]
MalignancyRiskCode = Literal["NO_SUSPICION", "LOW_SUSPICION", "CANNOT_EXCLUDE"]
RecommendationCode = Literal[
    "FOLLOWUP_3_MONTHS", "FOLLOWUP_6_MONTHS",
    "PROMPT_VISIT_ON_CHANGE", "NO_SHORT_TERM_FOLLOWUP_REQUIRED",
]
FinalAssessmentCode = Literal["NO_HIGH_GRADE_SUSPICION", "HIGH_GRADE_CANNOT_BE_EXCLUDED"]


class MedicalPayloadLesionV1(BaseModel):
    """
    One lesion group: lesion_numbers from Wideodermatoskop + one shared description.
    lesion_numbers must be non-empty and contain no duplicates.
    """
    model_config = ConfigDict(extra="allow")

    lesion_numbers: list[int] = Field(..., min_length=1, description="Wideodermatoskop lesion numbers in this group")
    dermatoscopic_features: list[DermatoscopicFeatureCode] = Field(default_factory=list)
    clinical_assessment: ClinicalAssessmentCode
    malignancy_risk: MalignancyRiskCode
    generated_text: str | None = Field(default=None, max_length=50000)
    edited_text: str | None = Field(default=None, max_length=50000)

    @model_validator(mode="after")
    def no_duplicate_lesion_numbers(self) -> "MedicalPayloadLesionV1":
        if len(self.lesion_numbers) != len(set(self.lesion_numbers)):
            raise ValueError("lesion_numbers must not contain duplicates")
        return self


class MedicalPayloadTemplateContextV1(BaseModel):
    model_config = ConfigDict(extra="allow")

    template_id: UUID | str | None = None
    template_name: str | None = None
    template_locale: str | None = None


class MedicalPayloadV1(BaseModel):
    """
    Full medical_payload v1. lesions may be empty only when overall_image_assessment=NO_CONTROL_NEEDED.
    """
    model_config = ConfigDict(extra="allow")

    schema_version: Literal[1] = 1
    authoring_locale: str = Field(default="de-DE", min_length=2, max_length=10)
    examination_scope: list[ExaminationScopeCode] = Field(default_factory=list)
    fitzpatrick_type: FitzpatrickTypeCode | None = None
    overall_image_assessment: OverallImageAssessmentCode = Field(default="NO_CONTROL_NEEDED")
    lesions: list[MedicalPayloadLesionV1] = Field(default_factory=list)
    recommendations: list[RecommendationCode] = Field(default_factory=list)
    final_assessment: FinalAssessmentCode = Field(default="NO_HIGH_GRADE_SUSPICION")
    summary_generated_text: str | None = Field(default=None, max_length=50000)
    summary_edited_text: str | None = Field(default=None, max_length=50000)
    template_context: MedicalPayloadTemplateContextV1 | dict | None = None

    @model_validator(mode="after")
    def lesions_empty_only_when_no_control_needed(self) -> "MedicalPayloadV1":
        if self.overall_image_assessment == "CONTROL_NEEDED" and len(self.lesions) == 0:
            raise ValueError("lesions must not be empty when overall_image_assessment is CONTROL_NEEDED")
        return self


def validate_medical_payload_v1(data: dict) -> dict:
    """
    Validate and return normalized dict for medical_payload when schema_version is 1.
    Raises pydantic.ValidationError if invalid.
    """
    model = MedicalPayloadV1.model_validate(data)
    return model.model_dump(mode="json")


_VALID_OVERALL = ("NO_CONTROL_NEEDED", "CONTROL_NEEDED")
_VALID_FINAL = ("NO_HIGH_GRADE_SUSPICION", "HIGH_GRADE_CANNOT_BE_EXCLUDED")


def validate_medical_payload_complete_for_publish(payload: dict | None, locale: str = "") -> None:
    """
    Sprawdza, czy medical_payload jest kompletny do publikacji (wszystkie wymagane pola wypełnione).
    Wymagane: sekcje 1–3, 10, 11 (examination_scope, fitzpatrick_type, overall_image_assessment,
    recommendations, final_assessment). Sekcja 4 (lesions) jest wymagana gdy overall_image_assessment=CONTROL_NEEDED
    (walidowane przy zapisie draftu).
    Raises DomainError z komunikatem w języku zgodnym z locale (de/en/pl).
    """
    from apps.core.api_error_i18n import OTHER_I18N_KEY_DEFAULT_EN
    from apps.core.exceptions import DomainError
    from apps.core.translation_service import get_translation_map, normalize_language_code

    if not payload or payload.get("schema_version") != 1:
        return
    lang = normalize_language_code(locale or "en")
    ui = get_translation_map(category="doctor", language_code=lang)

    def _msg(full_key: str) -> str:
        return ui.get(full_key) or OTHER_I18N_KEY_DEFAULT_EN.get(full_key, full_key)

    examination_scope = payload.get("examination_scope") or []
    if len(examination_scope) < 1:
        k = "doctor.msg_validation_examination_scope_required"
        raise DomainError(_msg(k), api_message_key=k)
    if payload.get("fitzpatrick_type") is None:
        k = "doctor.msg_validation_fitzpatrick_required"
        raise DomainError(_msg(k), api_message_key=k)
    overall = payload.get("overall_image_assessment")
    if overall not in _VALID_OVERALL:
        k = "doctor.msg_validation_overall_assessment_required"
        raise DomainError(_msg(k), api_message_key=k)
    recommendations = payload.get("recommendations") or []
    if len(recommendations) < 1:
        k = "doctor.msg_validation_recommendations_required"
        raise DomainError(_msg(k), api_message_key=k)
    final = payload.get("final_assessment")
    if final not in _VALID_FINAL:
        k = "doctor.msg_validation_final_assessment_required"
        raise DomainError(_msg(k), api_message_key=k)
