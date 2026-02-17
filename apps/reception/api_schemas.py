from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateQueueEntrySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_by_user_id: UUID
    form_locale: str = "de-DE"
    expires_in_minutes: int = Field(default=20, ge=1, le=240)
    tablet_device_id: UUID | None = None
