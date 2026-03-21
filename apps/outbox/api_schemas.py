from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from apps.core.api_utils import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT
from apps.outbox.models import OutboxEventType, OutboxStatus


class OutboxEventsQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OutboxStatus | None = None
    event_type: OutboxEventType | None = None
    retry_count_gte: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)


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
