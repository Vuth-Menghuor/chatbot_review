"""
FastAPI Application Factory - Retrieval service v2
Creates and configures the FastAPI application

Port: 8003 (see GDCE services architecture)

Service Role (from ORCHESTRATOR_V2_ARCHITECTURE.md):
  This service handles retrieval-based intents from the Orchestrator:
  - Intent.HS_CODE_LOOKUP    → /hs-code-lookup
  - Intent.DEFINITION        → /definition
  - Intent.POLICY_INQUIRY    → /policy-inquiry
  - Intent.GENERAL           → /general

Service Architecture (GDCE v2):
  Orchestrator (8001)
    ├─ Routes HS_CODE_LOOKUP → Retrieval Service (8003)
    ├─ Routes DEFINITION → Retrieval Service (8003)
    ├─ Routes POLICY_INQUIRY → Retrieval Service (8003)
    ├─ Routes GENERAL → Retrieval Service (8003)
    ├─ Routes CALCULATION → Calculator Service (8002)
    └─ Routes TRADE_QUERY → Trade Data Service (8004)

Data Flow:
  User Query (Natural Language)
    ↓
  Orchestrator (8001)
    ├─ Intent Detection
    ├─ Service Router
    ↓
  Retrieval Service (8003)
    ├─ Query Processing
    ├─ Qdrant Vector Search (172.25.3.243:6333)
    ├─ OpenSearch BM25 Search (172.25.3.243:9200)
    ↓
  Response to Orchestrator → User
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
  from .config import get_config
  from .core import QueryProcessor, RetrievalOrchestrator, RetrievalService
  from .infrastructure import VectorStoreClient, EmbeddingClient, DocumentRepository
  from .infrastructure.gemini_client import GeminiClient
  from .api import router
  from .api.endpoints import set_service
except ImportError:
  from config import get_config
  from core import QueryProcessor, RetrievalOrchestrator, RetrievalService
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
        title="Retrieval Service",
        description="Retrieval service for RAG pipeline",
        version="2.0.0",
        servers=[{"url": "http://localhost:8003", "description": "Local server"}],
    )
    
    # Add CORS middleware with configured origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize infrastructure components
    vector_store = VectorStoreClient(
        host=config.qdrant_host,
        port=config.qdrant_port,
      collection_name=config.qdrant_collection,
      timeout=config.qdrant_timeout,
      api_key=config.qdrant_api_key,
      default_score_threshold=0.1,  # Changed from config.similarity_threshold (was 0.5) - must be low to allow results through!
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
    
    # Initialize ranker (optional)
    ranker = None  # Can be implemented later
    
    # Initialize core services
    orchestrator = RetrievalOrchestrator(
        vector_store_client=vector_store,
        embedding_client=embeddings,
        document_repository=repository,
        ranker=ranker
    )
    
    query_processor = QueryProcessor()
    
    service = RetrievalService(
        query_processor=query_processor,
        retrieval_orchestrator=orchestrator,
        config=config,
      gemini_client=gemini_client,
    )
    
    # Set service in endpoints
    set_service(service)
    
    # Include routers with /v1 prefix (consistent with Calculator service)
    app.include_router(router, prefix="/v1")
    
    # Register startup/shutdown events
    @app.on_event("startup")
    @app.on_event("startup")
    async def on_startup():
      """Application startup — pre-warm everything so first request is fast."""
      import asyncio
      logger.info("Retrieval service starting up")

      # 1. Pre-load embedding model and warm HS corpus concurrently
      logger.info("Pre-loading embedding model and HS corpus in parallel...")
      try:
          embedding_task = asyncio.create_task(
              embeddings.embed_query("initialization test")
          )
          corpus_task = asyncio.create_task(
              service.prewarm()
          )
          test_embedding, _ = await asyncio.gather(
              embedding_task, corpus_task, return_exceptions=True
          )
          if isinstance(test_embedding, Exception):
              logger.warning(f"Embedding pre-load failed: {test_embedding}")
          else:
              logger.info(f"Embedding model ready (dim: {len(test_embedding)})")
      except Exception as e:
          logger.warning(f"Startup pre-warm error: {e}")

      # 2. Verify connections
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
