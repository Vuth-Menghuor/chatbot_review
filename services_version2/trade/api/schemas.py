"""Pydantic request/response models for trade_query API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """POST /query request body."""

    question: str = Field(
        ...,
        max_length=5000,
        description="Natural language question about Cambodia trade data",
    )
    extracted_params: Optional[dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "question": "Top 10 export countries in 2023",
            }
        }
    }


class TradeRecord(BaseModel):
    """A single trade record in the response."""

    hs_code: Optional[str] = None
    origin_country: Optional[str] = None
    destination_country: Optional[str] = None
    mode_of_transport: Optional[str] = None
    trade_value: Optional[float] = None
    currency: Optional[str] = "USD"
    trade_type: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "hs_code": "8517",
                "origin_country": "KH",
                "destination_country": "US",
                "mode_of_transport": "4",
                "trade_value": 124500000.0,
                "currency": "USD",
                "trade_type": "EX",
                "year": 2022,
            }
        }
    }


class TableData(BaseModel):
    """Structured table response for frontend grids."""

    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ChartDataset(BaseModel):
    """A single dataset series for graphs."""

    label: str
    data: list[float]


class VisualizationData(BaseModel):
    """Structured graphical response for charts (bar, line, pie)."""

    type: str  # "bar" | "line" | "pie"
    title: str
    labels: list[str]
    datasets: list[ChartDataset]


class TradeQueryResponse(BaseModel):
    """Standard response envelope for POST /query."""

    status: str = Field(default="success")
    count: int = Field(default=0)
    records: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    query_params: Optional[dict[str, Any]] = None
    table: Optional[TableData] = None
    visualization: Optional[VisualizationData] = None
    message: Optional[str] = None
    suggestion: Optional[str] = None
    total_trade_value: Optional[float] = Field(default=None, description="Total trade value in USD or query currency")
    currency: Optional[str] = Field(default="USD", description="Currency code (e.g. USD)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "count": 10,
                "records": [],
                "summary": {"total_trade_value": 124500000.0, "currency": "USD"},
                "metadata": {"intent": "ranking"},
                "query_params": {"year": 2023, "trade_direction": "EX"},
                "table": {
                    "columns": ["partner_country", "trade_value", "period"],
                    "rows": [{"partner_country": "US", "trade_value": 124500000.0, "period": "2023"}]
                },
                "visualization": {
                    "type": "bar",
                    "title": "Top Export Partners in 2023",
                    "labels": ["US"],
                    "datasets": [{"label": "Trade Value (USD)", "data": [124500000.0]}]
                }
            }
        }
    }


class DateClarificationPrompt(BaseModel):
    """Response when a date/period is missing."""

    status: str = Field(default="incomplete")
    message: str = Field(description="Explanation of what's needed")
    prompt: str = Field(description="Question to ask user for clarification")
    extracted_params: Optional[dict[str, Any]] = None
    suggestions: list[str] = Field(default_factory=lambda: [
        "Please specify a year (e.g., 2022, 2023)",
        "Or a range (e.g., 2020-2022)",
        "Or a month and year (e.g., March 2022)",
        "Or a quarter (e.g., Q1 2023)",
    ])


class ErrorResponse(BaseModel):
    """Standard error response."""

    error_code: str
    message: str
    field: Optional[str] = None
