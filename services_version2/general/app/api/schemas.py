"""
API Schemas - Request/Response models for General Retrieval Service
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class QueryRequest(BaseModel):
    """Request to retrieve documents."""
    query: str = Field(..., description="Search query", min_length=1, max_length=2000)
    top_k: Optional[int] = Field(10, description="Number of results", ge=1)
    session_id: Optional[str] = Field(None, description="Optional session identifier")
    collection: Optional[str] = Field(None, description="Collection to search. Defaults to gdce_docs")
    generate_answer: bool = Field(True, description="Generate a user-friendly final answer from retrieved documents")
    require_period_for_trade: bool = Field(
        True,
        description="If true, prompts for missing period when query appears to be trade data analytics",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What documents do I need to import goods into Cambodia?",
                "session_id": "session-123",
                "generate_answer": True
            }
        }


class DocumentResult(BaseModel):
    """A single document result."""
    id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Document content")
    score: float = Field(..., description="Relevance score", ge=0.0, le=1.0)
    source: str = Field(..., description="Data source (semantic/structured)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc-001",
                "content": "Importers must submit a customs declaration form...",
                "score": 0.92,
                "source": "semantic",
                "metadata": {"title": "Import Procedures FAQ"}
            }
        }


class QueryResponse(BaseModel):
    """Response with retrieved documents."""
    query: str = Field(..., description="Original query")
    status: str = Field(..., description="Response status (success/error/invalid_query/clarification_required)")
    documents: List[DocumentResult] = Field(..., description="Retrieved documents")
    total_count: int = Field(..., description="Total documents retrieved")
    semantic_count: Optional[int] = Field(None, description="Count from semantic search")
    structured_count: Optional[int] = Field(None, description="Count from structured search")
    final_answer: Optional[str] = Field(None, description="User-friendly final answer interpreted from retrieved content")
    answer_source: Optional[str] = Field(None, description="Source of final answer generation (gemini_llm/vllm/extractive_fallback/no_results)")
    session_id: Optional[str] = Field(None, description="Session identifier if provided")
    error: Optional[str] = Field(None, description="Error message if status is error")
    api_called: Optional[str] = Field(None, description="API route used for this response")
    collection_used: Optional[str] = Field(None, description="Collection used for retrieval")
    language: Optional[str] = Field(None, description="Detected query language")
    required_parameters: Optional[List[str]] = Field(None, description="Parameters required by this endpoint")
    missing_parameters: Optional[List[str]] = Field(None, description="Required parameters not provided")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional response metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What documents do I need to import goods into Cambodia?",
                "status": "success",
                "documents": [
                    {
                        "id": "doc-001",
                        "content": "Importers must submit a customs declaration form...",
                        "score": 0.92,
                        "source": "semantic"
                    }
                ],
                "total_count": 1,
                "semantic_count": 1,
                "structured_count": 0,
                "final_answer": "To import goods into Cambodia, you generally need a customs declaration, commercial invoice, and packing list.",
                "answer_source": "gemini_llm"
            }
        }


class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Overall status (healthy/degraded/unhealthy)")
    components: Dict[str, Dict[str, Any]] = Field(..., description="Component health details")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "components": {
                    "vector_store": {"status": "healthy", "host": "localhost", "port": 6334},
                    "embeddings": {"status": "healthy", "model": "BAAI/bge-m3"},
                    "repository": {"status": "healthy"}
                }
            }
        }
