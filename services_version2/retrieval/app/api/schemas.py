"""
API Schemas - Request/Response models for Retrieval service
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class QueryRequest(BaseModel):
    """Request to look up HS codes."""
    query: str = Field(..., description="Search query", min_length=1, max_length=2000)
    top_k: Optional[int] = Field(10, description="Number of results", ge=1)
    session_id: Optional[str] = Field(None, description="Optional session identifier")
    generate_answer: bool = Field(True, description="Generate a user-friendly final answer from retrieved documents")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "iphone 14 pro max",
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
                "content": "Cotton fabric is classified under HS code 5208",
                "score": 0.95,
                "source": "semantic",
                "metadata": {"hs_code": "5208"}
            }
        }


class QueryResponse(BaseModel):
    """Response with retrieved HS code documents."""
    query: str = Field(..., description="Original query")
    status: str = Field(..., description="Response status (success/error/invalid_query)")
    documents: List[DocumentResult] = Field(..., description="Retrieved documents")
    total_count: int = Field(..., description="Total documents retrieved")
    semantic_count: Optional[int] = Field(None, description="Count from semantic search")
    structured_count: Optional[int] = Field(None, description="Count from structured search")
    final_answer: Optional[str] = Field(None, description="User-friendly final answer interpreted from retrieved content")
    answer_source: Optional[str] = Field(None, description="Source of final answer generation")
    session_id: Optional[str] = Field(None, description="Session identifier if provided")
    error: Optional[str] = Field(None, description="Error message if status is error")
    api_called: Optional[str] = Field(None, description="API route used for this response")
    collection_used: Optional[str] = Field(None, description="Collection used for retrieval")
    language: Optional[str] = Field(None, description="Detected query language")
    required_parameters: Optional[List[str]] = Field(None, description="Parameters required by selected API mode")
    missing_parameters: Optional[List[str]] = Field(None, description="Required parameters not provided")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional response metadata")
    clarification_needed: bool = Field(False, description="True if the LLM determined the query is too generic to classify confidently")
    # clarifying_questions: Optional[List[str]] = Field(None, description="Suggested follow-up questions if clarification is needed")
    is_generic: bool = Field(False, description="True if the query was broad enough that more detail would refine the result")
    clarifying_note: Optional[str] = Field(None, description="Note explaining this is a best-guess classification")
    clarifying_questions: Optional[List[str]] = Field(None, description="Suggested follow-up questions to narrow the classification")
    reference_url: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "query": "HS code for cotton?",
                "status": "success",
                "documents": [
                    {
                        "id": "doc-001",
                        "content": "Cotton fabric is HS code 5208",
                        "score": 0.95,
                        "source": "semantic"
                    }
                ],
                "total_count": 1,
                "semantic_count": 1,
                "structured_count": 0,
                "final_answer": "",
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
                    "vector_store": {"status": "healthy", "host": "localhost", "port": 6333},
                }
            }
        }