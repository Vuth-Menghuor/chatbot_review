"""
API Endpoints - General Retrieval Service

Exposes a single retrieval endpoint for general/FAQ/definition/policy-style
queries: POST /retrieval/retrieve. This intentionally mirrors the route
path used by the HS-code retrieval service (port 8003) so callers can
switch the target host/port without changing the request path, while the
HS-specific endpoints (/hs-code-candidates, /hs-code-ranked) are not
present here.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, Any, List

from .schemas import QueryRequest, QueryResponse, HealthCheckResponse, DocumentResult
from prompts import render_prompt

try:
    from ..core import GeneralRetrievalService, AnswerGenerator
except ImportError:
    from ..core import GeneralRetrievalService, AnswerGenerator

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["general"])

# Service dependency (will be injected by app)
_service: Optional[GeneralRetrievalService] = None
_answer_generator: Optional[AnswerGenerator] = None


def set_service(service: GeneralRetrievalService):
    """Set the general retrieval service instance."""
    global _service, _answer_generator
    _service = service
    _answer_generator = AnswerGenerator(
        service.config,
        gemini_client=getattr(service, "gemini_client", None),
        cache_client=getattr(service, "cache_client", None),
    ) if service and service.config else None


def get_service() -> GeneralRetrievalService:
    """Get the current general retrieval service."""
    if _service is None:
        raise RuntimeError("General retrieval service not initialized")
    return _service


def transform_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Transform Qdrant/raw document to DocumentResult schema."""
    content = (
        doc.get("text") or
        doc.get("content") or
        doc.get("description") or
        doc.get("title") or
        ""
    )

    doc_id = str(doc.get("id") or doc.get("doc_id") or "unknown")
    score = doc.get("score", 0.5)
    source = doc.get("retrieval_source", "semantic")

    metadata = {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "source_url": doc.get("source_url"),
        "description": doc.get("description"),
    }
    for key, value in doc.items():
        if key not in ["id", "score", "content", "text", "retrieval_source"] and not key.startswith("_"):
            metadata[key] = value

    return {
        "id": doc_id,
        "content": str(content)[:1000] if content else "",
        "score": float(score) if score else 0.5,
        "source": source,
        "metadata": {k: v for k, v in metadata.items() if v is not None}
    }


async def build_final_answer(
    query: str,
    transformed_docs: List[Dict[str, Any]],
    generate_answer: bool,
    status: Optional[str] = None,
    clarification: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Build user-friendly final answer from documents."""
    if not generate_answer:
        return {"final_answer": None, "answer_source": None}

    if status == "clarification_required" and clarification:
        return {
            "final_answer": clarification,
            "answer_source": "clarification_required",
        }

    if _answer_generator is not None:
        generated = await _answer_generator.generate(
            query=query,
            documents=transformed_docs,
            intent="general",
            status=status,
        )
        return {
            "final_answer": generated.get("final_answer"),
            "answer_source": generated.get("answer_source"),
        }

    # Safe fallback when generator is unavailable
    if transformed_docs:
        snippet = transformed_docs[0].get("content", "")
        snippet = str(snippet).replace("\n", " ").strip()
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."
        return {
            "final_answer": render_prompt("extractive_prefix.txt", snippet=snippet) if snippet else None,
            "answer_source": "extractive_fallback",
        }

    return {
        "final_answer": render_prompt("no_results.txt"),
        "answer_source": "no_results",
    }


@router.post("/retrieval/retrieve", tags=["Intent: General"], response_model=QueryResponse)
async def retrieve(
    request: QueryRequest,
    service: GeneralRetrievalService = Depends(get_service)
) -> QueryResponse:
    """Retrieve documents matching the query (general / FAQ / definition / policy)."""
    try:
        logger.info(f"General retrieve request: {request.query[:100]}... (collection: {request.collection})")

        result = await service.retrieve(
            query=request.query,
            top_k=request.top_k,
            session_id=request.session_id,
            collection=request.collection,
            require_period_for_trade=request.require_period_for_trade,
        )

        transformed_docs = []
        for i, doc in enumerate(result.get("documents", []), 1):
            try:
                transformed_docs.append(transform_document(doc))
            except Exception as e:
                logger.error(f"Failed to transform document {i}: {e}", exc_info=True)
                continue

        answer_payload = await build_final_answer(
            query=request.query,
            transformed_docs=transformed_docs,
            generate_answer=request.generate_answer,
            status=result.get("status"),
            clarification=result.get("clarification"),
        )

        visibility = result.get("api_visibility", {})
        collection_used = visibility.get("collection_used") or request.collection or "gdce_docs"

        metadata = {
            "keywords": result.get("keywords", []),
            "clarification": result.get("clarification"),
        }
        metadata = {k: v for k, v in metadata.items() if v is not None}

        response_data = {
            "query": result.get("query", request.query),
            "status": result.get("status", "success"),
            "documents": transformed_docs,
            "total_count": len(transformed_docs),
            "semantic_count": result.get("semantic_count", 0),
            "structured_count": result.get("structured_count", 0),
            "session_id": result.get("session_id", request.session_id),
            "final_answer": (
                result.get("clarification")
                if result.get("status") == "clarification_required"
                else answer_payload.get("final_answer") or result.get("clarification")
            ),
            "answer_source": answer_payload.get("answer_source"),
            "api_called": "/retrieval/retrieve",
            "collection_used": collection_used,
            "language": result.get("language"),
            "required_parameters": ["query"],
            "missing_parameters": result.get("missing_parameters"),
            "metadata": metadata,
            "error": result.get("error"),
        }

        return QueryResponse(**response_data)

    except Exception as e:
        logger.error(f"Retrieve error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval failed: {str(e)}"
        )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(
    service: GeneralRetrievalService = Depends(get_service)
) -> HealthCheckResponse:
    """Check health of general retrieval service."""
    try:
        status = await service.health_check()
        return HealthCheckResponse(**status)
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthCheckResponse(
            status="unhealthy",
            components={"error": {"message": str(e)}}
        )


@router.get("/", tags=["Health"], response_model=dict)
def root():
    """Root endpoint showing available endpoints."""
    return {
        "service": "General Retrieval Service",
        "version": "1.0.0",
        "port": 8005,
        "endpoints": {
            "health": "GET /health",
            "retrieve": "POST /retrieval/retrieve",
            "swagger": "/docs",
            "openapi": "/openapi.json"
        },
        "description": (
            "Handles general/FAQ/definition/policy-style retrieval queries "
            "against a dedicated Qdrant instance, separate from the "
            "HS-code-focused retrieval service on port 8003."
        )
    }
