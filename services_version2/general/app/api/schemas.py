"""
API Schemas — Request / Response models for the General Retrieval Service.

Every public data structure consumed or produced by the REST API is defined
here as a Pydantic model. This keeps serialisation, validation, and OpenAPI
documentation in a single source of truth.
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class QueryRequest(BaseModel):
    """
    Inbound request to retrieve general documents.

    Supports an optional ``collection`` override for routing queries to
    specific Qdrant collections at request time.
    """

    query: str = Field(
        ...,
        description="Free-text search query (FAQ, definition, policy, etc.).",
        min_length=1,
        max_length=2000,
    )
    top_k: Optional[int] = Field(
        10,
        description="Maximum number of documents to retrieve.",
        ge=1,
    )
    session_id: Optional[str] = Field(
        None,
        description="Opaque session identifier for request tracing (optional).",
    )
    collection: Optional[str] = Field(
        None,
        description=(
            "Qdrant collection to search. Defaults to the configured "
            "collection (typically ``gdce_docs``)."
        ),
    )
    generate_answer: bool = Field(
        True,
        description=(
            "When True, the service will generate a human-readable final "
            "answer from the retrieved documents (via Gemini, vLLM, or "
            "extractive fallback). Set to False for raw document retrieval only."
        ),
    )
    require_period_for_trade: bool = Field(
        True,
        description=(
            "When True, queries that look like trade-data analytics will be "
            "prompted for a time period before retrieval proceeds."
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What documents do I need to import goods into Cambodia?",
                "session_id": "session-123",
                "generate_answer": True,
            }
        }


class DocumentResult(BaseModel):
    """
    A single retrieved document with its relevance metadata.

    This is the atomic unit of every search response — each document
    represents one match from the ``gdce_docs`` Qdrant collection.
    """

    id: str = Field(
        ...,
        description="Unique document identifier (Qdrant point ID).",
    )
    content: str = Field(
        ...,
        description="Full or truncated document text.",
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
            "'structured' (keyword/repository), or a composite label."
        ),
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional structured metadata (e.g. title, source_url).",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "doc-001",
                "content": "Importers must submit a customs declaration form...",
                "score": 0.92,
                "source": "semantic",
                "metadata": {"title": "Import Procedures FAQ"},
            }
        }


class QueryResponse(BaseModel):
    """
    Top-level response for ``POST /retrieval/retrieve``.

    Contains the retrieved document list, an optional generated answer,
    and metadata about the retrieval process.
    """

    query: str = Field(
        ...,
        description="Echo of the original query string.",
    )
    status: str = Field(
        ...,
        description=(
            "Response status: 'success', 'error', 'invalid_query', or "
            "'clarification_required'."
        ),
    )
    documents: List[DocumentResult] = Field(
        ...,
        description="Ordered list of retrieved documents (ranked by relevance).",
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
        description="Number of results contributed by structured (keyword) search.",
    )
    final_answer: Optional[str] = Field(
        None,
        description=(
            "Human-readable final answer generated from the retrieved "
            "documents (Gemini LLM, vLLM, or extractive fallback). None if "
            "``generate_answer`` was False or no results were found."
        ),
    )
    answer_source: Optional[str] = Field(
        None,
        description=(
            "Provenance of the final answer: 'gemini_llm', 'vllm', "
            "'extractive_fallback', 'no_results', or 'clarification_required'."
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
        description="Detected query language ('en' or 'km').",
    )
    required_parameters: Optional[List[str]] = Field(
        None,
        description="Parameters required by this endpoint.",
    )
    missing_parameters: Optional[List[str]] = Field(
        None,
        description="Required parameters that were not provided.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional response metadata (keywords, clarification).",
    )

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
                        "source": "semantic",
                    }
                ],
                "total_count": 1,
                "semantic_count": 1,
                "structured_count": 0,
                "final_answer": "To import goods into Cambodia, you generally need a customs declaration, commercial invoice, and packing list.",
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
        description="Per-component health details (vector_store, embeddings, repository).",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "components": {
                    "vector_store": {"status": "healthy", "host": "localhost", "port": 6334},
                    "embeddings": {"status": "healthy", "model": "BAAI/bge-m3"},
                    "repository": {"status": "healthy"},
                },
            }
        }
