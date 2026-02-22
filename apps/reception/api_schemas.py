from __future__ import annotations

import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Must match Patient model CheckConstraint patient_phone_format
PHONE_PATTERN = re.compile(r"^[0-9+() -]{7,20}$")


class CreateQueueEntrySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form_locale: str = "de-DE"
    expires_in_minutes: int = Field(default=120, ge=1, le=480)
    tablet_device_id: UUID | None = None
    android_id: str | None = Field(default=None, min_length=1, max_length=128)


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


class CreateTabletDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    android_id: str = Field(..., min_length=1, max_length=128)
    is_active: bool = True


class UpdateTabletDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    android_id: str | None = Field(default=None, min_length=1, max_length=128)
    is_active: bool | None = None


class CreateClinicSiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=120)
    is_active: bool = True


class UpdateClinicSiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None


class CreateConsultingRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinic_site_id: UUID
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=120)
    is_active: bool = True


class UpdateConsultingRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinic_site_id: UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None


def _validate_phone_format(v: str | None) -> str | None:
    if v is None:
        return v
    if not PHONE_PATTERN.fullmatch(v):
        raise ValueError("Phone must match format: digits, +, (), space, hyphen; 7-20 characters.")
    return v


class CreatePatientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    date_of_birth: date
    phone: str = Field(..., min_length=7, max_length=20)
    email: str = Field(..., min_length=3, max_length=254)
    doctolib_patient_id: str | None = Field(default=None, max_length=64)
    street: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country_code: str = Field(default="DE", min_length=2, max_length=2)
    external_source: str | None = Field(default=None, max_length=30)
    external_source_id: str | None = Field(default=None, max_length=100)

    @field_validator("phone", mode="after")
    @classmethod
    def phone_format(cls, v: str) -> str:
        return _validate_phone_format(v) or v


class UpdatePatientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    doctolib_patient_id: str | None = Field(default=None, max_length=64)
    street: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    external_source: str | None = Field(default=None, max_length=30)
    external_source_id: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    changed_by_user_id: UUID | None = None
    change_reason: str | None = Field(default=None, max_length=100)

    @field_validator("phone", mode="after")
    @classmethod
    def phone_format(cls, v: str | None) -> str | None:
        return _validate_phone_format(v)


class MergePatientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_patient_id: UUID
    source_action: str = Field(default="ARCHIVE", pattern="^(ARCHIVE|KEEP_ACTIVE)$")
    reason: str | None = Field(default=None, max_length=250)
    actor_user_id: UUID | None = None


class PatientsListQuery(BaseModel):
    """Query params for GET /api/v1/patients. Validates date_of_birth format (YYYY-MM-DD)."""

    model_config = ConfigDict(extra="forbid")

    date_of_birth: date | None = None

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def parse_date_of_birth(cls, v: str | date | None) -> date | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, date):
            return v
        try:
            return date.fromisoformat(v.strip())
        except ValueError:
            raise ValueError("Invalid date_of_birth format. Use YYYY-MM-DD.")
