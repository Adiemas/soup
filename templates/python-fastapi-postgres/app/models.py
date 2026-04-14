"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str = Field(description="overall status; 'ok' or 'degraded'")
    db: bool = Field(description="True when Postgres round-trip succeeded")
