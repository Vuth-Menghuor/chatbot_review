"""
API Schemas — Request / Response models for the Retrieval Service.

Every public data structure consumed or produced by the REST API is defined
here as a Pydantic model. This keeps serialisation, validation, and OpenAPI
documentation in a single source of truth.
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class QueryRequest(BaseModel):
    """
    Inbound request to look up HS codes for a product description.

    The ``query`` field is the only required parameter. All others have
    sensible defaults that can be overridden per-request.
    """

    query: str = Field(
        ...,
        description="Free-text product description or search query.",
        min_length=1,
        max_length=2000,
    )
    top_k: Optional[int] = Field(
        10,
        description="Maximum number of candidate HS codes to return.",
        ge=1,
    )
    session_id: Optional[str] = Field(
        None,
        description="Opaque session identifier for request tracing (optional).",
    )
    generate_answer: bool = Field(
        True,
        description=(
            "When True, the service will generate a human-readable final "
            "answer from the retrieved candidates (via Gemini or extractive "
            "ranking). Set to False for raw document retrieval only."
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "iphone 14 pro max",
                "session_id": "session-123",
                "generate_answer": True,
            }
        }


class DocumentResult(BaseModel):
    """
    A single retrieved HS-code document with its relevance metadata.

    This is the atomic unit of every search response — each document
    represents one candidate HS code entry from the Qdrant collection.
    """

    id: str = Field(
        ...,
        description="Unique document identifier (Qdrant point ID).",
    )
    content: str = Field(
        ...,
        description="Full or truncated document text (HS description).",
    )
    score: float = Field(
        ...,
        description="Relevance score, normalised to [0.0, 1.0].",
        ge=0.0,
        le=1.0,
    )
    source: str = Field(
        ...,
        description=(
            "Retrieval source — one of 'semantic' (vector search), "
            "'structured' (prefix scan), or a composite label."
        ),
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional structured metadata (e.g. hs_code, hs_prefix).",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc-001",
                "content": "Cotton fabric is classified under HS code 5208",
                "score": 0.95,
                "source": "semantic",
                "metadata": {"hs_code": "5208"},
            }
        }


class QueryResponse(BaseModel):
    """
    Top-level response for ``POST /hs-code-candidates``.

    Contains the retrieved document list, an optional generated answer,
    and metadata about the retrieval process (source, confidence, etc.).
    """

    query: str = Field(
        ...,
        description="Echo of the original query string.",
    )
    status: str = Field(
        ...,
        description="Response status: 'success', 'error', or 'invalid_query'.",
    )
    documents: List[DocumentResult] = Field(
        ...,
        description="Ordered list of retrieved HS-code candidate documents.",
    )
    total_count: int = Field(
        ...,
        description="Total number of retrieved documents.",
    )
    semantic_count: Optional[int] = Field(
        None,
        description="Number of results contributed by semantic (vector) search.",
    )
    structured_count: Optional[int] = Field(
        None,
        description="Number of results contributed by structured (prefix) search.",
    )
    final_answer: Optional[str] = Field(
        None,
        description=(
            "Human-readable final answer generated from the retrieved "
            "candidates (Gemini LLM or extractive ranking). None if "
            "``generate_answer`` was False or no results were found."
        ),
    )
    answer_source: Optional[str] = Field(
        None,
        description=(
            "Provenance of the final answer: 'gemini_llm', "
            "'extractive_ranked', or None."
        ),
    )
    session_id: Optional[str] = Field(
        None,
        description="Echo of the request's session_id, if provided.",
    )
    error: Optional[str] = Field(
        None,
        description="Error message when status is 'error'.",
    )
    api_called: Optional[str] = Field(
        None,
        description="Internal API route identifier for observability.",
    )
    collection_used: Optional[str] = Field(
        None,
        description="Name of the Qdrant collection queried.",
    )
    language: Optional[str] = Field(
        None,
        description="Detected query language (reserved for future use).",
    )
    required_parameters: Optional[List[str]] = Field(
        None,
        description="Parameters required by the selected API mode.",
    )
    missing_parameters: Optional[List[str]] = Field(
        None,
        description="Required parameters that were not provided.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional response metadata (prefix, source, confidence).",
    )
    clarification_needed: bool = Field(
        False,
        description=(
            "True if the LLM determined the query is too generic to classify "
            "confidently."
        ),
    )
    is_generic: bool = Field(
        False,
        description=(
            "True if the query was broad enough that more detail would "
            "meaningfully refine the result."
        ),
    )
    clarifying_note: Optional[str] = Field(
        None,
        description=(
            "Human-readable note explaining this is a best-guess "
            "classification when the query is generic."
        ),
    )
    clarifying_questions: Optional[List[str]] = Field(
        None,
        description=(
            "Backward-compatible alias for clarifications. Some orchestrator "
            "clients read this legacy key."
        ),
    )
    reference_url: Optional[str] = Field(
        None,
        description="URL to the official GDCE tariff lookup for verification.",
    )

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
                        "source": "semantic",
                    }
                ],
                "total_count": 1,
                "semantic_count": 1,
                "structured_count": 0,
                "final_answer": "Cotton fabric falls under HS 5208.",
                "answer_source": "gemini_llm",
            }
        }


class HealthCheckResponse(BaseModel):
    """
    Response model for ``GET /health``.

    Reports the overall service status and per-component health details
    so orchestration tools (Kubernetes, Docker, load balancers) can make
    routing and restart decisions.
    """

    status: str = Field(
        ...,
        description="Overall status: 'healthy', 'degraded', or 'unhealthy'.",
    )
    components: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="Per-component health details (e.g. vector_store, embeddings).",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "components": {
                    "vector_store": {"status": "healthy"},
                    "embeddings": {"status": "healthy"},
                },
            }
        }