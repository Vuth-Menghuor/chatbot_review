"""
FastAPI Application Factory — Retrieval Service (v2).

Port: 8003

This module wires together every infrastructure dependency (Qdrant,
embeddings, Gemini, Redis) and exposes the assembled FastAPI application
instance. The ``create_app()`` factory is the single point of assembly;
tests can call it with mocked sub-components to get an isolated app.

Service Scope
-------------
HS code classification exclusively against the ``gdce_hs_code`` Qdrant
collection, via two endpoints:

    - ``POST /hs-code-candidates`` — full retrieval + ranked answer.
    - ``POST /hs-code-ranked``   — simplified ranked-code list.

General / FAQ / definition / policy-style queries are handled by the
separate *general* retrieval service (port 8005) against its own Qdrant
instance and the ``gdce_docs`` collection — this service never touches that
collection.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Import resilience — the service can be run from different working
# directories (e.g. ``python -m services_version2.retrieval.app.app`` vs
# ``uvicorn app.app:app``). The ``try/except`` block handles both absolute
# (package) and relative (local) import styles.
# ---------------------------------------------------------------------------
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
    Assemble and return a fully configured FastAPI application.

    Responsibilities
    ----------------
    1. Load configuration from environment / ``.env``.
    2. Instantiate infrastructure clients (Qdrant, embeddings, Gemini, Redis).
    3. Wire the ``RetrievalService`` and inject it into the API layer.
    4. Register startup / shutdown lifecycle hooks.
    5. Mount the API router.

    Returns
    -------
    FastAPI
        Configured application instance, ready to serve.
    """
    config = get_config()
    logger.info("Configuration loaded: %s", config.to_dict())

    # -- FastAPI app --------------------------------------------------------
    app = FastAPI(
        title="Retrieval Service (HS Code Classification)",
        description=(
            "HS code classification service — semantic + structured "
            "retrieval against gdce_hs_code"
        ),
        version="2.0.0",
        servers=[{"url": "http://localhost:8003", "description": "Local server"}],
    )

    # -- CORS — origins are restricted via config, never wildcard -----------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Infrastructure clients ---------------------------------------------
    # Qdrant vector store — the single source of truth for HS code documents.
    vector_store = VectorStoreClient(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.qdrant_hs_code_collection,
        timeout=config.qdrant_timeout,
        api_key=config.qdrant_api_key,
        default_score_threshold=0.1,  # aggressive floor to prune noise
    )

    # Embedding model — lazy-loaded on first use; falls back to keyword-based
    # embeddings if the sentence-transformer model cannot be loaded.
    embeddings = EmbeddingClient(model_name=config.query_embedding_model)

    # Gemini LLM — optional; when disabled or unconfigured the service falls
    # back to extractive (lexical) answer ranking.
    gemini_client = None
    if config.gemini_enabled and config.gemini_api_key:
        logger.info("Initializing Gemini client (model: %s)", config.gemini_model)
        gemini_client = GeminiClient(
            api_key=config.gemini_api_key,
            model=config.gemini_model,
        )
    else:
        logger.info("Gemini client disabled or GEMINI_API_KEY not configured")

    # Retrieval orchestrator — thin wrapper around vector store + embeddings.
    orchestrator = RetrievalOrchestrator(
        vector_store_client=vector_store,
        embedding_client=embeddings,
    )

    # Redis cache — fail-open: if Redis is unavailable, cache calls return
    # misses rather than raising errors.
    cache_client = CacheClient(config.redis_host, config.redis_port)

    # High-level service — owns corpus loading, prefix lookup, candidate
    # scoring, and health reporting.
    retrieval_service = RetrievalService(
        retrieval_orchestrator=orchestrator,
        config=config,
        gemini_client=gemini_client,
        cache_client=cache_client,
    )

    # -- Wire service into API layer ----------------------------------------
    set_service(retrieval_service)
    app.include_router(router)

    # -- Lifecycle: startup -------------------------------------------------
    @app.on_event("startup")
    async def on_startup():
        """
        Pre-warm embedding model and HS corpus in parallel so the first
        client request does not pay the cold-start penalty.

        Also performs health checks against Qdrant and the embedding model
        so operators can see readiness status in the logs immediately.
        """
        import asyncio

        logger.info("Retrieval service starting up")

        # Run embedding warm-up and corpus pre-load concurrently.
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
                logger.warning("Embedding pre-load failed: %s", test_embedding)
            else:
                logger.info("Embedding model ready (dim: %d)", len(test_embedding))
        except Exception as e:
            logger.warning("Startup pre-warm error: %s", e)

        # Report dependency health for operator visibility.
        vs_health = await vector_store.health()
        logger.info("Vector store health: %s", vs_health)

        emb_health = await embeddings.health()
        logger.info("Embeddings health: %s", emb_health)

        logger.info("Startup complete — service ready")

    # -- Lifecycle: shutdown ------------------------------------------------
    @app.on_event("shutdown")
    async def on_shutdown():
        """Graceful shutdown hook — currently a no-op; reserve for cleanup."""
        logger.info("Retrieval service shutting down")

    return app


# ---------------------------------------------------------------------------
# Module-level application instance.
# Uvicorn references this as ``app.app:app``.
# ---------------------------------------------------------------------------
app = create_app()