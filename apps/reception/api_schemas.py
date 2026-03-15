from __future__ import annotations

import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    assigned_doctor_id: UUID | None = None
    shift_code: str = "FULL_DAY"
    source: str = "MANUAL"
    created_by_user_id: UUID


class UpdateDailyQueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None, pattern="^(OPEN|CLOSED)$")
    assigned_doctor_id: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def at_least_one_field(cls, data: dict) -> dict:
        if isinstance(data, dict) and "status" not in data and "assigned_doctor_id" not in data:
            raise ValueError("At least one of status or assigned_doctor_id must be provided.")
        return data


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
    clinic_site_id: UUID | None = Field(
        default=None,
        description="Przypisana placówka (ClinicSite); tablet widzi tylko kolejki tej placówki. Bez przypisania tablet nie wyświetli kolejek.",
    )


class UpdateTabletDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    android_id: str | None = Field(default=None, min_length=1, max_length=128)
    is_active: bool | None = None
    clinic_site_id: UUID | None = Field(
        default=None,
        description="Przypisana placówka; null = odpinanie od placówki.",
    )


class CreateClinicSiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=120)
    is_active: bool = True
    pdf_import_default_consulting_room_id: UUID | None = None
    pdf_import_shift_code: str = "FULL_DAY"


class UpdateClinicSiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    pdf_import_default_consulting_room_id: UUID | None = None
    pdf_import_shift_code: str | None = None


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
    is_active: bool | None = None
    changed_by_user_id: UUID | None = None
    change_reason: str | None = Field(default=None, max_length=100)

    @field_validator("phone", mode="after")
    @classmethod
    def phone_format(cls, v: str | None) -> str | None:
        return _validate_phone_format(v)

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
