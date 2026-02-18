from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)
