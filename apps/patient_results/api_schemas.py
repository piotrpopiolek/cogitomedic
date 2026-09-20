"""Pydantic request contracts for patient-results portal API."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_DOB_AGE_DAYS = 120 * 365


class PortalOtpIdentityFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=1, max_length=32)
    date_of_birth: date
    last_name: str | None = Field(default=None, max_length=100)

    @field_validator("phone", mode="before")
    @classmethod
    def strip_phone(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("last_name", mode="before")
    @classmethod
    def empty_last_name_to_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def parse_date_of_birth(cls, value: object) -> object:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return value.strip()[:10]
        return value

    @field_validator("date_of_birth", mode="after")
    @classmethod
    def date_of_birth_in_range(cls, value: date) -> date:
        today = timezone.now().date()
        if value > today or value < today - timedelta(days=_MAX_DOB_AGE_DAYS):
            raise ValueError("date_of_birth must be YYYY-MM-DD.")
        return value


class RequestOtpRequest(PortalOtpIdentityFields):
    captcha_token: str = ""

    @field_validator("captcha_token", mode="before")
    @classmethod
    def strip_captcha_token(cls, value: object) -> object:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return value


class VerifyOtpRequest(PortalOtpIdentityFields):
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("otp_code", mode="before")
    @classmethod
    def strip_otp_code(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value
