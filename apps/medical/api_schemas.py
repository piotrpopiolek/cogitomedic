from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateMedicalDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_entry_id: UUID
    intake_form_id: UUID
    created_by_user_id: UUID


class SaveDraftMedicalDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_by_user_id: UUID
    medical_payload_schema_version: int = Field(ge=1)
    medical_payload: dict
    diagnosis_code: str | None = None
    procedure_code: str | None = None


class PublishMedicalDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publish_request_id: UUID
    published_by_user_id: UUID
