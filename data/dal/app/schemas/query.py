"""Pydantic schemas for query request parsing and internal normalized model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FilterItem(BaseModel):
    """A single parsed filter: FIELD:op:value."""

    field: str
    operator: str
    value: str


class SortItem(BaseModel):
    """A single parsed sort directive: FIELD:direction."""

    field: str
    direction: str = "asc"


class NormalizedQuery(BaseModel):
    """Internal normalized query model after parsing and validation."""

    dataset: str
    version: str
    frequency: str
    dimensions: list[str]
    measures: list[str]
    start_period: str | None
    end_period: str | None
    period: str | None = None
    filters: list[FilterItem] = Field(default_factory=list)
    sort: list[SortItem] = Field(default_factory=list)
    limit: int = 100
    offset: int = 0
    

class NormalizedDatasetInfoQuery(BaseModel):
    """Normalized query model for metadata endpoint, without measures and filters."""

    dataset: str
    version: str | None