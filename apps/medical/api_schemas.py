from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FavoriteLesionGroupPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    dermatoscopic_features: list[str] = Field(default_factory=list, max_length=20)
    clinical_assessment: str = Field(min_length=1, max_length=64)
    malignancy_risk: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=5000)


class MedicalPayloadMinimal(BaseModel):
    """
    Minimal contract for medical_payload stored in DB (§6: must have schema_version).
    Full v1 shape (authoring_locale, lesions, etc.) is in api-plan; this enforces versioning.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(ge=1)


class CreateMedicalDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_entry_id: UUID
    intake_form_id: UUID
    created_by_user_id: UUID | None = None  # ignored; session user is used


class SaveDraftMedicalDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_by_user_id: UUID | None = None  # ignored; session user is used
    medical_payload_schema_version: int = Field(ge=1)
    medical_payload: MedicalPayloadMinimal
    diagnosis_code: str | None = None
    procedure_code: str | None = None
    # explicit "amend" intent is required to start a revision of an
    # already PUBLISHED document. ``edit`` is the legacy DRAFT-only behaviour.
    # Wire type is ``str`` so invalid values reach ``save_draft_document_version`` and
    # produce ``other.api.invalid_save_draft_intent`` (distinct from amend guardrail).
    intent: str = Field(
        default="edit",
        description=(
            'Save intent: must be exactly "edit" or "amend". Use "amend" only when the '
            "document is already PUBLISHED and the user confirms starting a revision. "
            "Any other string yields HTTP 400 with `error_key` "
            "`other.api.invalid_save_draft_intent`."
        ),
    )


class PublishMedicalDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publish_request_id: UUID
    published_by_user_id: UUID | None = None  # ignored; session user is used
    resend_sms: bool = False  # US-010: when republishing, send SMS again to patient
    publish_locale: str = Field(
        min_length=2, max_length=10, pattern=r"^(de|en|pl)(-[A-Z]{2})?$"
    )


class DoctorTemplateListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_user_id: UUID | None = None  # ignored; session user is used for filter
    template_locale: str | None = None
    include_inactive: bool = False


class DoctorTemplateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_user_id: UUID | None = None  # ignored; session user is used
    name: str = Field(min_length=1, max_length=120)
    template_locale: str = Field(min_length=2, max_length=10)
    template_body: str = Field(min_length=1)
    lesion_group_favorites: list[FavoriteLesionGroupPreset] = Field(
        default_factory=list
    )
    is_global: bool = False
    clinic_site_id: UUID | None = None
    is_active: bool = True


class DoctorTemplateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_user_id: UUID | None = None  # ignored; session user is used
    name: str | None = Field(default=None, min_length=1, max_length=120)
    template_locale: str | None = Field(default=None, min_length=2, max_length=10)
    template_body: str | None = Field(default=None, min_length=1)
    lesion_group_favorites: list[FavoriteLesionGroupPreset] | None = None
    is_active: bool | None = None


class RetryProcessingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(
        default="manual retry from doctor panel", min_length=3, max_length=200
    )
