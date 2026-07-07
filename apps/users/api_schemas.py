from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.core.api_schemas import OffsetPaginationQueryParams
from apps.core.api_utils import parse_bool_query
from apps.users.models import VALID_STAFF_ROLES


class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)
    android_id: str | None = Field(default=None, min_length=1, max_length=128)


class CreateStaffUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=254)
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=100)
    phone_number: str | None = Field(default=None, min_length=7, max_length=20)
    role: str = Field(pattern="^(RECEPTION|DOCTOR|ADMIN|TABLET|MANAGER|ACCOUNTING)$")
    preferred_locale: str = Field(
        default="de-DE", pattern="^(de-DE|en-GB|pl-PL)$", max_length=10
    )
    is_staff: bool = True
    is_active: bool = True
    password: str = Field(min_length=8, max_length=256)


class UpdateStaffUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, min_length=3, max_length=254)
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone_number: str | None = Field(default=None, min_length=7, max_length=20)
    role: str | None = Field(
        default=None, pattern="^(RECEPTION|DOCTOR|ADMIN|TABLET|MANAGER|ACCOUNTING)$"
    )
    preferred_locale: str | None = Field(
        default=None, pattern="^(de-DE|en-GB|pl-PL)$", max_length=10
    )
    is_staff: bool | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


class UpdateStaffUserClinicSitesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinic_site_ids: list[UUID]


class StaffUsersListQueryParams(OffsetPaginationQueryParams):
    """Query params for GET /api/v1/staff-users."""

    role: str | None = None
    is_active: bool | None = None
    search: str | None = Field(default=None, max_length=254)

    @field_validator("role", mode="before")
    @classmethod
    def empty_role_to_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("role", mode="after")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_STAFF_ROLES:
            raise ValueError("Invalid role query parameter.")
        return value

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_is_active(cls, value: object) -> bool | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            parsed = parse_bool_query(value)
            if parsed is None:
                raise ValueError("Invalid is_active query parameter.")
            return parsed
        raise ValueError("Invalid is_active query parameter.")

    @field_validator("search", mode="before")
    @classmethod
    def empty_search_to_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value
