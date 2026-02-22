from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class PublishMedicalDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publish_request_id: UUID
    published_by_user_id: UUID | None = None  # ignored; session user is used
    resend_sms: bool = False  # US-010: when republishing, send SMS again to patient


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
    is_global: bool = False
    is_active: bool = True


class DoctorTemplateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_user_id: UUID | None = None  # ignored; session user is used
    name: str | None = Field(default=None, min_length=1, max_length=120)
    template_locale: str | None = Field(default=None, min_length=2, max_length=10)
    template_body: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class GenerateTextRequest(BaseModel):
    """Request for POST /medical-documents/{id}/generate-text. Payload with lesions and options."""
    model_config = ConfigDict(extra="allow")

    medical_payload_schema_version: int = Field(ge=1)
    authoring_locale: str = Field(default="de-DE", min_length=2, max_length=10)
    template_id: UUID | None = None
    medical_payload: dict = Field(default_factory=dict)
