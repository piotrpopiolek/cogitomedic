from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
