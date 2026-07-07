"""Pydantic models for dataset concept metadata (parsed from JSONB)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

class QueryCase(BaseModel):
    base: str
    case: dict[str, str]


class CodeListConcept(BaseModel):
    code: str
    label: str | None = None
    

class SQLValueConcept(BaseModel):
    sql: str


class Metadata(BaseModel):
    description: str | None = None
    type: str | None = None
    auto_generate: bool = Field(alias="auto-generate", default=False)
    data: list | SQLValueConcept | None = None


class FrequencyConcept(BaseModel):
    code: str
    query: QueryCase | str
    default: str
    metadata: Metadata | None = None


class PeriodFilterConcept(BaseModel):
    query: QueryCase | str | dict[str, str]
    pattern_test: dict[str, str] | None = Field(alias="pattern-test", default=None)
    

class PeriodConcept(BaseModel):
    code: str
    query: QueryCase | str | dict[str, str]
    pattern_test: dict[str, str] | None = Field(alias="pattern-test", default=None)
    default: str | None = None
    filters: dict[str, PeriodFilterConcept] | None = Field(default=None)
    metadata: Metadata | None = None


class DimensionConcept(BaseModel):
    code: str
    query: QueryCase | str | dict[str, str]
    aggregate: str | None = None
    pattern_test: dict[str, str] | None = Field(alias="pattern-test", default=None)
    default: str | None = None
    metadata: Metadata | None = None
    

class MeasureUnit(BaseModel):
    code: str
    query: QueryCase | str | dict[str, str]
    pattern_test: dict[str, str] | None = Field(alias="pattern-test", default=None)
    metadata: Metadata | None = None


class MeasureConcept(BaseModel):
    code: str
    query: QueryCase | str | dict[str, str]
    aggregate: str = "SUM"
    unit: MeasureUnit | None = None
    pattern_test: dict[str, str] | None = Field(alias="pattern-test", default=None)
    metadata: Metadata | None = None


class JoinConcept(BaseModel):
    table: str
    type: str = "inner"
    on: str


class ResultFilterConcept(BaseModel):
    query: QueryCase | str | dict[str, str]
    pattern_test: dict[str, str] | None = Field(alias="pattern-test", default=None)

    model_config = {"populate_by_name": True}


class SourceConcept(BaseModel):
    connection_key: str = Field(alias="connection-key") 
    table: str
    join: list[JoinConcept] = Field(default_factory=list)
    result_filter: list[ResultFilterConcept] | None = Field(default=None, alias="result-filter")

    model_config = {"populate_by_name": True}


class FilterKeyConcept(BaseModel):
    query: QueryCase | str | dict[str, str]
    pattern_test: dict[str, str] | None = Field(alias="pattern-test", default=None)
    default: str | None = None

    model_config = {"populate_by_name": True}


class SecurityConcept(BaseModel):
    allow_raw_sql: bool = Field(alias="allow-raw-sql", default=False)


class DatasetConcept(BaseModel):
    """Full dataset concept parsed from the JSONB metadata."""
    
    dataset_code: str = Field(alias="dataset-code")
    version: str
    frequency: FrequencyConcept
    period: PeriodConcept
    dimensions: list[DimensionConcept]
    measures: list[MeasureConcept]
    source: SourceConcept
    filters: dict[str, FilterKeyConcept]
    security: SecurityConcept = Field(default_factory=SecurityConcept)