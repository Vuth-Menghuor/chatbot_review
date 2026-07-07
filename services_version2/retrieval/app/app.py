"""
FastAPI Application Factory - Retrieval service v2 (HS code classification only)

Port: 8003

Service Role:
  Handles HS code classification exclusively against the gdce_hs_code Qdrant
  collection, via two endpoints:
    - POST /hs-code-candidates
    - POST /hs-code-ranked

  General/FAQ/definition/policy-style queries are handled by the separate
  general retrieval service (port 8005) against its own Qdrant instance
  and the gdce_docs collection — this service never touches that collection.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from .config import get_config
    from .rag.retrieval import RetrievalOrchestrator
    from .rag.service import RetrievalService
    from .vectorstore.vector_store import VectorStoreClient
    from .embeddings.embeddings import EmbeddingClient
    from .llm.gemini_client import GeminiClient
    from .cache.redis_client import CacheClient
    from .api import router
    from .api.endpoints import set_service
except ImportError:
    from config import get_config
    from rag.retrieval import RetrievalOrchestrator
    from rag.service import RetrievalService
    from vectorstore.vector_store import VectorStoreClient
    from embeddings.embeddings import EmbeddingClient
    from llm.gemini_client import GeminiClient
    from cache.redis_client import CacheClient
    from api import router
    from api.endpoints import set_service

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI app instance
    """
    config = get_config()
    logger.info(f"Configuration loaded: {config.to_dict()}")

    app = FastAPI(
        title="Retrieval Service (HS Code Classification)",
        description="HS code classification service — semantic + structured retrieval against gdce_hs_code",
        version="2.0.0",
        servers=[{"url": "http://localhost:8003", "description": "Local server"}],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    vector_store = VectorStoreClient(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.qdrant_hs_code_collection,
        timeout=config.qdrant_timeout,
        api_key=config.qdrant_api_key,
        default_score_threshold=0.1,
    )

    embeddings = EmbeddingClient(model_name=config.query_embedding_model)

    gemini_client = None
    if config.gemini_enabled and config.gemini_api_key:
        logger.info(f"Initializing Gemini client (model: {config.gemini_model})")
        gemini_client = GeminiClient(api_key=config.gemini_api_key, model=config.gemini_model)
    else:
        logger.info("Gemini client disabled or GEMINI_API_KEY not configured")

    orchestrator = RetrievalOrchestrator(
        vector_store_client=vector_store,
        embedding_client=embeddings,
    )

    cache_client = CacheClient(config.redis_host, config.redis_port)

    retrieval_service = RetrievalService(
        retrieval_orchestrator=orchestrator,
        config=config,
        gemini_client=gemini_client,
        cache_client=cache_client,
    )

    set_service(retrieval_service)
    app.include_router(router)

    @app.on_event("startup")
    async def on_startup():
        """Application startup — pre-warm everything so first request is fast."""
        import asyncio
        logger.info("Retrieval service starting up")

        logger.info("Pre-loading embedding model and HS corpus in parallel...")
        try:
            embedding_task = asyncio.create_task(
                embeddings.embed_query("initialization test")
            )
            corpus_task = asyncio.create_task(retrieval_service.prewarm())
            test_embedding, _ = await asyncio.gather(
                embedding_task, corpus_task, return_exceptions=True
            )
            if isinstance(test_embedding, Exception):
                logger.warning(f"Embedding pre-load failed: {test_embedding}")
            else:
                logger.info(f"Embedding model ready (dim: {len(test_embedding)})")
        except Exception as e:
            logger.warning(f"Startup pre-warm error: {e}")

        vs_health = await vector_store.health()
        logger.info(f"Vector store health: {vs_health}")

        emb_health = await embeddings.health()
        logger.info(f"Embeddings health: {emb_health}")
        logger.info("Startup complete — service ready")

    @app.on_event("shutdown")
    async def on_shutdown():
        """Application shutdown."""
        logger.info("Retrieval service shutting down")

    return app


# Application instance
app = create_app()