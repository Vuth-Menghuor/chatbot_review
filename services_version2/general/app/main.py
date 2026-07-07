"""
FastAPI application entrypoint for the general retrieval service.
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

app = FastAPI(
    title="General Retrieval Service",
    version="1.0.0",
    description="General/FAQ/definition/policy retrieval service",
)


def build_service() -> GeneralRetrievalService:
    """Build the service stack used by the API router."""
    config = get_config()

    cache_client = CacheClient(config.redis_host, config.redis_port, config.redis_enabled)

    embedding_client = EmbeddingClient(config.query_embedding_model)
    vector_store_client = VectorStoreClient(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.qdrant_collection,
        timeout=config.qdrant_timeout,
        api_key=config.qdrant_api_key,
        default_score_threshold=config.similarity_threshold,
    )
    document_repository = DocumentRepository()
    retrieval_orchestrator = RetrievalOrchestrator(
        vector_store_client=vector_store_client,
        embedding_client=embedding_client,
        document_repository=document_repository,
    )
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


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize the shared service instance before handling requests."""
    service = build_service()
    set_service(service)
    app.state.service = service
    logger.info("General Retrieval Service initialized")


app.include_router(router)