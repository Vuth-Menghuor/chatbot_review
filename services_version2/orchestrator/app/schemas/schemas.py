"""
API Schemas for Orchestrator service
Defines request/response models and validation
Structure for Frontend
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum


class Citation(BaseModel):
    """Citation/Reference to source material."""
    doc_id: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    score: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "HS_CODE_0101",
                "title": "HS Code 01.01 Classification",
                "snippet": "Live animals, items classified...",
                "score": 0.92
            }
        }


class TableData(BaseModel):
    """Structured table response for frontend grids."""
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)


class ChartDataset(BaseModel):
    """A single dataset series for graphs."""
    label: str
    data: List[float]


class VisualizationData(BaseModel):
    """Structured graphical response for charts (bar, line, pie)."""
    type: str  # "bar" | "line" | "pie"
    title: str
    labels: List[str]
    datasets: List[ChartDataset]


class QueryRequest(BaseModel):
    """Request model for query endpoint."""
    question: str = Field(
        ...,
        min_length=2,
        max_length=2000,
        description="User question"
    )
    session_id: Optional[str] = Field(
        None,
        description="Optional session identifier"
    )
    user_id: Optional[str] = Field(
        None,
        description="Optional user identifier from API Layer"
    )
    project_id: Optional[str] = Field(
        None,
        description="Optional project identifier from API Layer"
    )
    
    @validator('question')
    def validate_question(cls, v):
        """Validate question input."""
        if not v or not v.strip():
            raise ValueError("Question cannot be empty")
        if len(v.strip()) < 2:
            raise ValueError("Question must be at least 2 characters")
        if len(v) > 2000:
            raise ValueError("Question must not exceed 2000 characters")
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the HS code for chicken meat?",
                "session_id": "session_123",
                "user_id": "user_abc",
                "project_id": "project_xyz"
            }
        }



class QueryResponse(BaseModel):
    """Response model for query endpoint."""
    request_id: str = Field(
        ...,
        description="Unique request identifier"
    )
    session_id: Optional[str] = Field(
        None,
        description="Session identifier — echo this back in subsequent requests to preserve multi-turn context"
    )
    question: str = Field(
        ...,
        description="Original user question"
    )
    answer: Optional[str] = Field(
        None,
        description="Answer or response"
    )
    intent: Optional[str] = Field(
        None,
        description="Detected query intent"
    )
    status: str = Field(
        ...,
        description="Workflow status (completed, failed, clarification_required)"
    )
    citations: List[Citation] = Field(
        default_factory=list,
        description="Supporting citations"
    )
    clarifications: List[str] = Field(
        default_factory=list,
        description="Clarifications required from user"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Errors encountered"
    )
    latency_ms: float = Field(
        0.0,
        description="Query processing latency in milliseconds"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )
    table: Optional[TableData] = Field(
        None,
        description="Structured table response for frontend grids"
    )
    visualization: Optional[VisualizationData] = Field(
        None,
        description="Structured graphical response for charts (bar, line, pie)"
    )
    message: Optional[str] = Field(
        None,
        description="Natural language answer text"
    )
    suggestion: Optional[List[str]] = Field(
        None,
        description="Follow-up chips array (frontend contract)"
    )
    summary: Optional[Dict[str, Any]] = Field(
        None,
        description="Summary metadata (e.g. data_quality truncation note)"
    )
    summary_metrics: Optional[Dict[str, Any]] = Field(
        None,
        description="Deprecated: legacy summary metrics"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req_123456",
                "question": "What is the HS code for chicken meat?",
                "answer": "HS Code 0207.13.00 covers poultry meat...",
                "intent": "definition",
                "status": "completed",
                "citations": [
                    {
                        "doc_id": "HS_0207",
                        "title": "HS Classification 0207",
                        "snippet": "Meat of poultry...",
                        "score": 0.95
                    }
                ],
                "latency_ms": 234.5,
                "metadata": {}
            }
        }


class CalculationRequest(BaseModel):
    """Request model for calculation service."""
    question: str = Field(
        ...,
        description="Calculation question"
    )
    hs_code: Optional[str] = Field(
        None,
        description="HS code for calculation"
    )
    cif_value: Optional[float] = Field(
        None,
        description="CIF value for calculation"
    )
    origin_country: Optional[str] = Field(
        None,
        description="Origin country code"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the import tax on 100 USD of electronics from China?",
                "hs_code": "8471.30.00",
                "cif_value": 100.0,
                "origin_country": "CN"
            }
        }


class CalculationResponse(BaseModel):
    """Response model for calculation."""
    result: Optional[Dict[str, Any]] = Field(
        None,
        description="Calculation result"
    )
    breakdown: Optional[Dict[str, float]] = Field(
        None,
        description="Tax breakdown"
    )
    total_tax: Optional[float] = Field(
        None,
        description="Total tax amount"
    )
    currency: str = Field(
        default="KHR",
        description="Result currency"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "result": {
                    "customs_duty": 10.0,
                    "special_tax": 5.0,
                    "vat": 15.0
                },
                "breakdown": {
                    "cd_rate": 0.10,
                    "st_rate": 0.05,
                    "vat_rate": 0.10
                },
                "total_tax": 30.0,
                "currency": "KHR"
            }
        }


class HealthCheckResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str = Field(
        ...,
        description="Service status (healthy, degraded, unhealthy)"
    )
    version: str = Field(
        ...,
        description="Service version"
    )
    timestamp: str = Field(
        ...,
        description="Current timestamp"
    )
    services: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Status of dependent services"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "2.0.0",
                "timestamp": "2024-01-15T10:30:45.123Z",
                "services": {
                    "retrieval": {
                        "status": "healthy",
                        "latency_ms": 50
                    },
                    "calculator": {
                        "status": "healthy",
                        "latency_ms": 30
                    },
                    "trade_data": {
                        "status": "degraded",
                        "latency_ms": 2000
                    }
                }
            }
        }


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(
        ...,
        description="Error message"
    )
    error_code: str = Field(
        ...,
        description="Error code"
    )
    request_id: Optional[str] = Field(
        None,
        description="Related request ID"
    )
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional error details"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Service temporarily unavailable",
                "error_code": "SERVICE_UNAVAILABLE",
                "request_id": "req_123",
                "details": {
                    "service": "calculator",
                    "reason": "Connection timeout"
                }
            }
        }


class TradeQuerySlots(BaseModel):
    """Structured slot parameters for trade queries."""
    product: Optional[str] = Field(default=None, description="Commodity or product entity")
    flow: Optional[str] = Field(default=None, description="Trade flow direction (IMPORT/EXPORT)")
    time_period: Optional[str] = Field(default=None, description="Explicit year, quarter, or date range")
    partner_country: Optional[str] = Field(default=None, description="Trading partner country")


class IntentClassificationResult(BaseModel):
    """Result of first-layer intent classification."""
    intent: str = Field(..., description="Detected intent label")
    confidence: float = Field(..., description="Classification confidence score")
    is_safe: bool = Field(default=True, description="Safety check status")
    is_on_topic: bool = Field(default=True, description="Domain scope check status")
    slots: Optional[TradeQuerySlots] = Field(default=None, description="Trade query slots (null for non-trade intents)")

