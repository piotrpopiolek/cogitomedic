from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.core.api_schemas import ListLimitQueryParams
from apps.outbox.models import OutboxEventType, OutboxStatus


class OutboxEventsQueryParams(ListLimitQueryParams):
    model_config = ConfigDict(extra="forbid")

    status: OutboxStatus | None = None
    event_type: OutboxEventType | None = None
    retry_count_gte: int = Field(default=0, ge=0)

    @field_validator("retry_count_gte", mode="before")
    @classmethod
    def parse_retry_count_gte(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return 0
        return value


class ProcessOutboxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=100, ge=1, le=500)


class RetryOutboxEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class RetentionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    older_than_days: int = Field(default=30, ge=1, le=3650)
