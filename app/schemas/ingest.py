from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    ok: bool
    message: str
    counts: dict[str, int] = Field(default_factory=dict)
    status: dict[str, str] = Field(default_factory=dict)


class IngestTaskResponse(BaseModel):
    ok: bool
    message: str
    task: dict[str, Any] = Field(default_factory=dict)
