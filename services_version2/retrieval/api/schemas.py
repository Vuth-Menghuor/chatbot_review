"""
API Schemas - Request/Response models for Retrieval service
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class QueryRequest(BaseModel):
    """Request to retrieve documents."""
    query: str = Field(..., description="Search query", min_length=1, max_length=2000)
    top_k: Optional[int] = Field(10, description="Number of results", ge=1)
    session_id: Optional[str] = Field(None, description="Optional session identifier")
    collection: Optional[str] = Field(None, description="Collection to search (gdce_docs, gdce_hs_code). If None, uses default gdce_docs")
    intent: Optional[str] = Field(None, description="Intent type from orchestrator (e.g., hs_code_lookup, definition, policy_query, general)")
    generate_answer: bool = Field(True, description="Generate a user-friendly final answer from retrieved documents")
    hs_mode: Optional[str] = Field(
        "best",
        description="HS response mode: best (single most relevant), compare, or select",
        pattern="^(best|compare|select)$",
    )
    compare_codes: Optional[List[str]] = Field(None, description="HS codes to compare when hs_mode=compare")
    selected_code: Optional[str] = Field(None, description="Selected HS code when hs_mode=select")
    require_period_for_trade: bool = Field(
        True,
        description="If true, prompts for missing period when query appears to be trade data analytics",
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "Iphone 14 promax",
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
    """Response with retrieved documents."""
    query: str = Field(..., description="Original query")
    status: str = Field(..., description="Response status (success/error/invalid_query)")
    documents: List[DocumentResult] = Field(..., description="Retrieved documents")
    total_count: int = Field(..., description="Total documents retrieved")
    semantic_count: Optional[int] = Field(None, description="Count from semantic search")
    structured_count: Optional[int] = Field(None, description="Count from structured search")
    final_answer: Optional[str] = Field(None, description="User-friendly final answer interpreted from retrieved content")
    answer_source: Optional[str] = Field(None, description="Source of final answer generation (llm/extractive_fallback/no_results)")
    session_id: Optional[str] = Field(None, description="Session identifier if provided")
    error: Optional[str] = Field(None, description="Error message if status is error")
    api_called: Optional[str] = Field(None, description="API route used for this response")
    collection_used: Optional[str] = Field(None, description="Collection used for retrieval")
    language: Optional[str] = Field(None, description="Detected query language")
    required_parameters: Optional[List[str]] = Field(None, description="Parameters required by selected API mode")
    missing_parameters: Optional[List[str]] = Field(None, description="Required parameters not provided")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional response metadata")
    
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
                "final_answer": "Cotton fabric is generally classified under HS code heading 5208.",
                "answer_source": "llm"
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
                    "embeddings": {"status": "healthy", "model": "all-MiniLM-L6-v2"},
                    "repository": {"status": "healthy"}
                }
            }
        }
