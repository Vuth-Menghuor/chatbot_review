"""Universal DAL request and response schemas."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DALRequest(BaseModel):
    """Normalized request payload sent to DAL."""

    intent: str = Field(..., description="Query intent, e.g. ranking, summary, comparison")
    filters: dict[str, Any] = Field(default_factory=dict)
    metrics: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    version: Optional[str] = None
    start_period: Optional[str] = None
    end_period: Optional[str] = None
    period: Optional[str] = None
    frequency: Optional[str] = None
    sort: Optional[str] = None
    limit: int = 1000
    offset: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)


class DALResponse(BaseModel):
    """Normalized response payload from DAL."""

    records: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    count: int = 0
