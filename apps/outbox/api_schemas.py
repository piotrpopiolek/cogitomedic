from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from apps.outbox.models import OutboxEventType, OutboxStatus


class OutboxEventsQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OutboxStatus | None = None
    event_type: OutboxEventType | None = None
    retry_count_gte: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class ProcessOutboxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=100, ge=1, le=500)


class RetryOutboxEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)
