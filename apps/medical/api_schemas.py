from __future__ import annotations

from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.core.api_schemas import OffsetPaginationQueryParams


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


class CreateMedicalDocumentWithoutIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_entry_id: UUID
    created_by_user_id: UUID | None = None  # ignored; session user is used


class PaperIntakeAuthorizationRequest(BaseModel):
    """Body for POST (authorize) and DELETE (revoke) paper-intake authorization on a queue entry."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(
        min_length=10,
        max_length=500,
        description=(
            "Justification for authorize (POST) or revoke (DELETE), 10–500 characters. "
            "DELETE uses the same `application/json` body as POST (including this field); "
            "it is not a body-less delete."
        ),
    )


class EditSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["edit", "amend"] = "edit"
    edit_session_token: UUID | None = None
    edit_session_request_id: UUID | None = None
    expected_edit_session_revision: int | None = Field(default=None, ge=0)
    reclaim_confirmed: bool = False


class SaveDraftMedicalDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_by_user_id: UUID | None = None  # ignored; session user is used
    medical_payload_schema_version: int = Field(ge=1)
    medical_payload: MedicalPayloadMinimal
    diagnosis_code: str | None = None
    procedure_code: str | None = None
    edit_session_token: UUID
    expected_draft_revision: int = Field(ge=0)
    draft_save_request_id: UUID
    # explicit "amend" intent is required when a pending revision is already open.
    # Starting a revision on clean PUBLISHED requires POST …/edit-session purpose=amend.
    # Wire type is ``str`` so invalid values reach ``save_draft_document_version`` and
    # produce ``other.api.invalid_save_draft_intent`` (distinct from amend guardrail).
    intent: str = Field(
        default="edit",
        description=(
            'Save intent: must be exactly "edit" or "amend". Use "amend" when saving '
            "an open pending revision on a PUBLISHED document. Starting a revision "
            "requires POST …/edit-session with purpose=amend. Any other string yields "
            "HTTP 400 with `error_key` `other.api.invalid_save_draft_intent`."
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
    edit_session_token: UUID
    expected_draft_revision: int = Field(ge=0)


class DiscardRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edit_session_token: UUID
    expected_draft_revision: int = Field(ge=0)


class ExternalUploadSelectAttachmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: UUID


class ExternalUploadRevisionStartRequest(BaseModel):
    """POST body for ``/external-upload/revision/start`` (empty JSON object)."""

    model_config = ConfigDict(extra="forbid")


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


class MedicalDocumentAuditTrailQueryParams(OffsetPaginationQueryParams):
    """Query params for GET /api/v1/medical-documents/{id}/audit-trail."""

    pass
