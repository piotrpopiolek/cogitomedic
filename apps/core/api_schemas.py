"""Shared Pydantic query/body contracts for API v1."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.core.constants import DEFAULT_LIST_LIMIT
from apps.core.list_pagination import coerce_allowed_page_size, coerce_page_number


class OffsetPaginationQueryParams(BaseModel):
    """Standard offset pagination for list endpoints (``page`` + ``page_size``)."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=DEFAULT_LIST_LIMIT)

    @field_validator("page", mode="before")
    @classmethod
    def normalize_page(cls, value: object) -> int:
        return coerce_page_number(value)

    @field_validator("page_size", mode="before")
    @classmethod
    def normalize_page_size(cls, value: object) -> int:
        return coerce_allowed_page_size(value)


class ListLimitQueryParams(BaseModel):
    """Standard ``limit`` param for reception-style capped lists."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_LIST_LIMIT)

    @field_validator("limit", mode="before")
    @classmethod
    def normalize_limit(cls, value: object) -> int:
        return coerce_allowed_page_size(value)
