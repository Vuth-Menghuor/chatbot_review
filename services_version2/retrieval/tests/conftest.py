"""
Test fixtures and configuration for Retrieval service tests
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import List, Dict, Any

from services_version2.retrieval.config import RetrievalConfig
from services_version2.retrieval.core import QueryProcessor, RetrievalOrchestrator, RetrievalService
from services_version2.retrieval.infrastructure import VectorStoreClient, EmbeddingClient, DocumentRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_config() -> MagicMock:
    """Create mock configuration."""
    config = MagicMock(spec=RetrievalConfig)
    config.qdrant_host = "localhost"
    config.qdrant_port = 6333
    config.qdrant_collection_name = "test-documents"
    config.qdrant_hs_collection_name = "test-hs-codes"
    config.embedding_model = "all-MiniLM-L6-v2"
    config.top_k_default = 10
    config.top_k_max = 50
    config.request_timeout = 30
    config.cors_origins = ["*"]
    config.log_level = "INFO"
    return config


@pytest.fixture
def mock_vector_store() -> AsyncMock:
    """Create mock vector store client."""
    client = AsyncMock(spec=VectorStoreClient)
    client.collection_name = "test-documents"
    client.client = MagicMock()
    
    async def mock_search(
        embedding: List[float],
        top_k: int = 10,
        score_threshold=None,
        collection_name: str = None,
    ):
        return [
            {
                "id": "doc-001",
                "score": 0.95,
                "content": "Test document 1",
                "source": "test"
            },
            {
                "id": "doc-002",
                "score": 0.85,
                "content": "Test document 2",
                "source": "test"
            }
        ]
    
    async def mock_health():
        return {
            "status": "healthy",
            "host": "localhost",
            "port": 6333,
            "collection": "test-documents",
            "collection_exists": True
        }
    
    client.search = mock_search
    client.health = mock_health
    return client


@pytest.fixture
def mock_embedding_client() -> AsyncMock:
    """Create mock embedding client."""
    client = AsyncMock(spec=EmbeddingClient)
    
    async def mock_embed_query(query: str) -> List[float]:
        # Return dummy embedding
        return [0.1] * 384
    
    async def mock_health():
        return {
            "status": "healthy",
            "model": "all-MiniLM-L6-v2",
            "embedding_dim": 384
        }
    
    client.embed_query = mock_embed_query
    client.health = mock_health
    return client


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create mock document repository."""
    repo = AsyncMock(spec=DocumentRepository)
    
    async def mock_search_by_keywords(keywords: List[str], limit: int = 10):
        return [
            {
                "id": "structured-001",
                "content": "Structured result 1",
                "score": 0.9
            }
        ]
    
    async def mock_health():
        return {
            "status": "healthy",
            "components": {
                "database": {"status": "healthy"},
                "search": {"status": "healthy"}
            }
        }
    
    repo.search_by_keywords = mock_search_by_keywords
    repo.health = mock_health
    return repo


@pytest.fixture
def query_processor() -> QueryProcessor:
    """Create QueryProcessor instance."""
    return QueryProcessor()


@pytest.fixture
def retrieval_orchestrator(mock_vector_store, mock_embedding_client, mock_repository) -> RetrievalOrchestrator:
    """Create RetrievalOrchestrator with mocked dependencies."""
    return RetrievalOrchestrator(
        vector_store_client=mock_vector_store,
        embedding_client=mock_embedding_client,
        document_repository=mock_repository,
        ranker=None
    )


@pytest.fixture
def retrieval_service(query_processor, retrieval_orchestrator, mock_config) -> RetrievalService:
    """Create RetrievalService with mocked dependencies."""
    return RetrievalService(
        query_processor=query_processor,
        retrieval_orchestrator=retrieval_orchestrator,
        config=mock_config
    )


@pytest.fixture
def sample_query() -> str:
    """Sample query for testing."""
    return "What is the HS code for cotton fabric?"


@pytest.fixture
def sample_processed_query(query_processor, sample_query):
    """Sample processed query."""
    return query_processor.process(sample_query)
