from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConsentAcceptanceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_definition_id: UUID
    accepted: bool
    selected_option_code: str | None = None
    selected_option_codes: list[str] = Field(default_factory=list)


class UpdateConsentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consents: list[ConsentAcceptanceItem] = Field(default_factory=list)


class SignatureUploadRequest(BaseModel):
    """Base64-encoded signature image (e.g. data:image/png;base64,...)."""

    model_config = ConfigDict(extra="forbid")

    signature_base64: str = Field(..., min_length=1)


class AnamnesisAnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_code: str
    selected_option_codes: list[str] = Field(default_factory=list)
    free_text: str | None = None


class UpdateAnamnesisPayloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anamnesis_schema_version: int = Field(ge=1)
    answers: list[AnamnesisAnswerPayload] = Field(default_factory=list)


class SubmitIntakeFormRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submitted_by_user_id: UUID | None = None


class BodyMapPointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    side: str = Field(..., pattern="^(front|back)$")
    label: str | None = None


class UpdateBodyMapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_map_schema_version: int = Field(ge=1)
    body_map_data: list[BodyMapPointPayload] = Field(default_factory=list)


# --- Intake outbox (list / retry / process) ---


class IntakeOutboxEventsQueryParams(BaseModel):
    """Query params for GET /api/v1/intake-outbox-events."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    event_type: str | None = None
    retry_count_gte: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class ProcessIntakeOutboxRequest(BaseModel):
    """Request body for POST /api/v1/operations/intake-outbox/process."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=100, ge=1, le=500)


class RetryIntakeOutboxEventRequest(BaseModel):
    """Request body for POST /api/v1/intake-outbox-events/{id}/retry."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)
