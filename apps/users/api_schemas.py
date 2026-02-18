from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class CreateStaffUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=254)
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=100)
    phone_number: str | None = Field(default=None, min_length=7, max_length=20)
    role: str = Field(pattern="^(RECEPTION|DOCTOR|ADMIN)$")
    preferred_locale: str = Field(default="de-DE", max_length=10)
    is_staff: bool = True
    is_active: bool = True
    password: str = Field(min_length=8, max_length=256)


class UpdateStaffUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, min_length=3, max_length=254)
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone_number: str | None = Field(default=None, min_length=7, max_length=20)
    role: str | None = Field(default=None, pattern="^(RECEPTION|DOCTOR|ADMIN)$")
    preferred_locale: str | None = Field(default=None, max_length=10)
    is_staff: bool | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)
