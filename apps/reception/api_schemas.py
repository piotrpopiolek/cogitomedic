from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateQueueEntrySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_by_user_id: UUID
    form_locale: str = "de-DE"
    expires_in_minutes: int = Field(default=20, ge=1, le=240)
    tablet_device_id: UUID | None = None


class CreateDailyQueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_date: date
    clinic_site_id: UUID
    consulting_room_id: UUID
    shift_code: str = "FULL_DAY"
    source: str = "MANUAL"
    created_by_user_id: UUID


class UpdateDailyQueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., pattern="^(OPEN|CLOSED)$")


class CreateQueueEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    created_by_user_id: UUID
    visit_external_id: str | None = None
    appointment_time: datetime | None = None
    notes: str | None = None


class UpdateQueueEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_status: str | None = None
    notes: str | None = None
