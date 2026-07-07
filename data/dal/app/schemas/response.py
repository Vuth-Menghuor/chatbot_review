"""Pydantic response models — success and error envelopes."""

from __future__ import annotations

from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field


class PeriodInfo(BaseModel):
    from_: str | None = Field(None, alias="from")
    to: str | None = None

    model_config = {"populate_by_name": True}


class PaginationInfo(BaseModel):
    limit: int
    offset: int


class CacheInfo(BaseModel):
    hit: bool
    ttl_seconds: int | None = None


class MetaInfo(BaseModel):
    latency_ms: float


class QueryResponse(BaseModel):
    """Successful query response envelope."""

    request_id: str
    dataset: str
    version: str
    frequency: str
    dimensions: list[str]
    measures: list[str]
    period: PeriodInfo
    pagination: PaginationInfo
    cache: CacheInfo
    meta: MetaInfo
    row_count: int
    data: list[dict[str, Any]]

    model_config = {"populate_by_name": True}


class CodeConcept(BaseModel):
    code: str
    label: str | None = None


class ColumnInfo(BaseModel):
    code: str
    description: str | None = None
    type: str | None = None
    auto_generate: bool = False
    data: list[CodeConcept] | None = None


class DatasetInfoResponse(BaseModel):
    """Successful dataset detail response envelope."""

    request_id: str
    dataset: str
    version: str
    frequency: ColumnInfo | None = None
    period: ColumnInfo | None = None
    dimensions: list[ColumnInfo] = Field(default_factory=list)
    measures: list[ColumnInfo] = Field(default_factory=list)
    cache: CacheInfo
    meta: MetaInfo

    model_config = {"populate_by_name": True}


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Error response envelope."""

    request_id: str
    error: ErrorDetail
    

class CreateDatasetResponse(BaseModel):
    """Response payload after dataset creation."""

    request_id: str
    dataset_id: str
    dataset_code: str
    name: str
    description: str | None = None
    is_public: bool
    status: str
    created_at: datetime
