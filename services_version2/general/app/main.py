"""
FastAPI Application Entrypoint — General Retrieval Service.

Port: 8005

This module wires together every infrastructure dependency (Qdrant,
embeddings, Gemini, Redis, document repository) and exposes the assembled
FastAPI application instance. The ``build_service()`` factory is called
at startup; the resulting ``GeneralRetrievalService`` is injected into
the API layer via ``set_service()``.

Service Scope
-------------
General / FAQ / definition / policy queries against the ``gdce_docs``
Qdrant collection. This service never touches the HS-code collection
(``gdce_hs_code``) — that is handled by the retrieval service on port 8003.
"""

import logging

from fastapi import FastAPI

from .api.endpoints import router, set_service
from .cache.redis_client import CacheClient
from .config.config import get_config
from .embeddings.embeddings import EmbeddingClient
from .llm.gemini_client import GeminiClient
from .rag.query import QueryProcessor
from .rag.retrieval import RetrievalOrchestrator
from .rag.service import GeneralRetrievalService
from .repositories.repositories import DocumentRepository
from .vectorstore.vector_store import VectorStoreClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application instance — Uvicorn references this as ``app.main:app``.
# ---------------------------------------------------------------------------
app = FastAPI(
    title="General Retrieval Service",
    version="1.0.0",
    description="General/FAQ/definition/policy retrieval service",
)


def build_service() -> GeneralRetrievalService:
    """
    Assemble the full service stack.

    Instantiates every infrastructure component (Redis cache, embedding
    model, Qdrant client, document repository, retrieval orchestrator,
    Gemini LLM client) and returns a ready-to-use ``GeneralRetrievalService``.

    Called once at application startup — not per-request.
    """
    config = get_config()

    # -- Redis cache (fail-open) -------------------------------------------
    cache_client = CacheClient(
        config.redis_host, config.redis_port, config.redis_enabled
    )

    # -- Embedding model (BAAI/bge-m3 by default, 1024-dim) ----------------
    embedding_client = EmbeddingClient(config.query_embedding_model)

    # -- Qdrant vector store (dedicated instance, port 6334) ---------------
    vector_store_client = VectorStoreClient(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.qdrant_collection,
        timeout=config.qdrant_timeout,
        api_key=config.qdrant_api_key,
        default_score_threshold=config.similarity_threshold,
    )

    # -- Document repository (optional structured search backend) ----------
    document_repository = DocumentRepository()

    # -- Retrieval orchestrator (wires vector search + structured search) --
    retrieval_orchestrator = RetrievalOrchestrator(
        vector_store_client=vector_store_client,
        embedding_client=embedding_client,
        document_repository=document_repository,
    )

    # -- Gemini LLM client (optional — falls back to extractive answers) ---
    gemini_client = None
    if config.gemini_enabled and config.gemini_api_key:
        gemini_client = GeminiClient(
            api_key=config.gemini_api_key,
            model=config.gemini_model or "gemini-3.1-flash-lite",
        )

    return GeneralRetrievalService(
        query_processor=QueryProcessor(),
        retrieval_orchestrator=retrieval_orchestrator,
        config=config,
        gemini_client=gemini_client,
        cache_client=cache_client,
    )


# ---------------------------------------------------------------------------
# Lifecycle: startup
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event() -> None:
    """
    Build the service stack once at startup and inject it into the API layer.

    The service is also stored on ``app.state.service`` for introspection
    within the ASGI app scope (e.g. middleware, custom instrumentation).
    """
    service = build_service()
    set_service(service)
    app.state.service = service
    logger.info("General Retrieval Service initialized")


# -- Mount the API router ----------------------------------------------------
app.include_router(router)