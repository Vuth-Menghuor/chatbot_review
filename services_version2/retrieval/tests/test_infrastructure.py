"""
Tests for Infrastructure components
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
class TestVectorStoreClient:
    """Test VectorStoreClient (with mocks since actual Qdrant not available in tests)."""
    
    async def test_vector_store_health(self, mock_vector_store):
        """Test vector store health check."""
        health = await mock_vector_store.health()
        
        assert health["status"] == "healthy"
        assert health["host"] == "localhost"
        assert health["port"] == 6333
    
    async def test_vector_store_search(self, mock_vector_store):
        """Test vector store search."""
        embedding = [0.1] * 384
        results = await mock_vector_store.search(embedding=embedding, top_k=10)
        
        assert isinstance(results, list)
        assert len(results) > 0
        assert "id" in results[0]
        assert "score" in results[0]


@pytest.mark.asyncio
class TestEmbeddingClient:
    """Test EmbeddingClient."""
    
    async def test_embedding_client_embed_query(self, mock_embedding_client):
        """Test query embedding."""
        embedding = await mock_embedding_client.embed_query("cotton fabric")
        
        assert isinstance(embedding, list)
        assert len(embedding) == 384
    
    async def test_embedding_client_health(self, mock_embedding_client):
        """Test embedding client health check."""
        health = await mock_embedding_client.health()
        
        assert health["status"] == "healthy"
        assert "model" in health
        assert "embedding_dim" in health


@pytest.mark.asyncio
class TestDocumentRepository:
    """Test DocumentRepository."""
    
    async def test_repository_search_by_keywords(self, mock_repository):
        """Test keyword search."""
        results = await mock_repository.search_by_keywords(["cotton", "fabric"])
        
        assert isinstance(results, list)
        assert len(results) > 0
    
    async def test_repository_health(self, mock_repository):
        """Test repository health check."""
        health = await mock_repository.health()
        
        assert health["status"] == "healthy"
        assert "components" in health


@pytest.mark.asyncio
class TestInfrastructureIntegration:
    """Integration tests for infrastructure components."""
    
    async def test_vector_store_and_embeddings_together(self, mock_embedding_client, mock_vector_store):
        """Test embeddings and vector store work together."""
        # Get embedding
        query_embedding = await mock_embedding_client.embed_query("test query")
        
        # Use embedding to search
        results = await mock_vector_store.search(embedding=query_embedding, top_k=5)
        
        assert len(results) > 0
    
    async def test_all_components_healthy(self, mock_vector_store, mock_embedding_client, mock_repository):
        """Test all infrastructure components are healthy."""
        health1 = await mock_vector_store.health()
        health2 = await mock_embedding_client.health()
        health3 = await mock_repository.health()
        
        assert health1["status"] == "healthy"
        assert health2["status"] == "healthy"
        assert health3["status"] == "healthy"
