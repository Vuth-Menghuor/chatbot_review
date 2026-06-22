"""
FastAPI Application Factory - General Retrieval Service
Port: 8005

Service Role:
  This service handles general/FAQ/definition/policy-style retrieval
  queries against the 'gdce_docs' collection, on its OWN dedicated
  Qdrant instance (default port 6334). It is intentionally separate
  from the HS-code-focused retrieval service (port 8003, Qdrant 6333)
  so that general document growth and traffic never compete with or
  pollute HS code vector search.

Data Flow:
  User Query (Natural Language)
    ↓
  Orchestrator (8001)
    ↓ routes general/FAQ/definition/policy queries here
  General Retrieval Service (8005)
    ├─ Query Processing
    ├─ Qdrant Vector Search (dedicated instance, default :6334)
    ├─ Lexical reranking
    ├─ Gemini answer generation
    ↓
  Response to Orchestrator → User
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from .config import get_config
    from .core import QueryProcessor, RetrievalOrchestrator, GeneralRetrievalService
    from .infrastructure import VectorStoreClient, EmbeddingClient, DocumentRepository
    from .infrastructure.gemini_client import GeminiClient
    from .api import router
    from .api.endpoints import set_service
except ImportError:
    from config import get_config
    from core import QueryProcessor, RetrievalOrchestrator, GeneralRetrievalService
    from infrastructure import VectorStoreClient, EmbeddingClient, DocumentRepository
    from infrastructure.gemini_client import GeminiClient
    from api import router
    from api.endpoints import set_service

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI app instance
    """
    # Load configuration first
    config = get_config()
    logger.info(f"Configuration loaded: {config.to_dict()}")

    # Create app
    app = FastAPI(
        title="General Retrieval Service",
        description="General-purpose document retrieval service for FAQ/definition/policy-style queries",
        version="1.0.0",
        servers=[{"url": "http://localhost:8005", "description": "Local server"}],
    )

    # Add CORS middleware with configured origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize infrastructure components — points at the general
    # service's OWN Qdrant instance (default :6334), not the HS-code one.
    vector_store = VectorStoreClient(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.qdrant_collection,
        timeout=config.qdrant_timeout,
        api_key=config.qdrant_api_key,
        default_score_threshold=0.1,
    )

    embeddings = EmbeddingClient(
        model_name=config.query_embedding_model
    )

    repository = DocumentRepository()

    gemini_client = None
    if config.gemini_enabled and config.gemini_api_key:
        logger.info(f"Initializing Gemini client (model: {config.gemini_model})")
        gemini_client = GeminiClient(
            api_key=config.gemini_api_key,
            model=config.gemini_model,
        )
    else:
        logger.info("Gemini client disabled or GEMINI_API_KEY not configured")

    # Initialize core services
    orchestrator = RetrievalOrchestrator(
        vector_store_client=vector_store,
        embedding_client=embeddings,
        document_repository=repository,
        ranker=None,
    )

    query_processor = QueryProcessor()

    service = GeneralRetrievalService(
        query_processor=query_processor,
        retrieval_orchestrator=orchestrator,
        config=config,
        gemini_client=gemini_client,
    )

    # Set service in endpoints
    set_service(service)

    # Include routers
    app.include_router(router)

    # Register startup/shutdown events
    @app.on_event("startup")
    async def on_startup():
        """Application startup — pre-warm embedding model and verify connections."""
        logger.info("General retrieval service starting up")

        try:
            test_embedding = await embeddings.embed_query("initialization test")
            logger.info(f"Embedding model ready (dim: {len(test_embedding)})")
        except Exception as e:
            logger.warning(f"Embedding pre-load failed: {e}")

        vs_health = await vector_store.health()
        logger.info(f"Vector store health: {vs_health}")

        emb_health = await embeddings.health()
        logger.info(f"Embeddings health: {emb_health}")
        logger.info("Startup complete — service ready")

    @app.on_event("shutdown")
    async def on_shutdown():
        """Application shutdown."""
        logger.info("General retrieval service shutting down")

    return app


# Application instance
app = create_app()
