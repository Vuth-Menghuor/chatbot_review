"""
Tests for Retrieval Service business logic
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
class TestRetrievalService:
    """Test RetrievalService class."""

    async def test_fetch_hs_documents_by_prefix(self, retrieval_service):
        """Test exact 6-digit HS prefix fetching from cached corpus."""
        retrieval_service._load_hs_corpus = lambda collection_name: [
            {"id": 1, "hs_code": "87034011", "text": "Passenger vehicle electric"},
            {"id": 2, "hs_code": "87043112", "text": "Pickup truck CKD"},
        ]

        docs = retrieval_service.fetch_hs_documents_by_prefix("870340", "test-collection", limit=10)

        assert len(docs) == 1
        assert docs[0]["hs_code"] == "87034011"
        assert docs[0]["retrieval_source"] == "structured_prefix_scan"
    
    async def test_retrieve_success(self, retrieval_service, sample_query):
        """Test successful retrieval."""
        result = await retrieval_service.retrieve(
            query=sample_query,
            top_k=10
        )
        
        assert result["status"] == "success"
        assert result["query"] == sample_query
        assert "documents" in result
        assert isinstance(result["documents"], list)
    
    async def test_retrieve_respects_config_defaults(self, retrieval_service, sample_query):
        """Test that service respects config defaults."""
        result = await retrieval_service.retrieve(
            query=sample_query,
            top_k=None  # Should use config default
        )
        
        assert result["status"] == "success"
    
    async def test_retrieve_respects_top_k_limit(self, retrieval_service, sample_query, mock_config):
        """Test that service respects top_k limit."""
        result = await retrieval_service.retrieve(
            query=sample_query,
            top_k=5
        )
        
        assert len(result["documents"]) <= 5
    
    async def test_retrieve_caps_top_k_to_max(self, retrieval_service, sample_query, mock_config):
        """Test that service caps top_k to maximum."""
        # Request more than max
        result = await retrieval_service.retrieve(
            query=sample_query,
            top_k=1000
        )
        
        assert len(result["documents"]) <= mock_config.top_k_max
    
    async def test_retrieve_invalid_query(self, retrieval_service):
        """Test retrieval with invalid query."""
        result = await retrieval_service.retrieve(
            query=""  # Invalid empty query
        )
        
        assert result["status"] == "invalid_query"
        assert len(result["documents"]) == 0
        assert "error" in result
    
    async def test_retrieve_with_session_id(self, retrieval_service, sample_query):
        """Test retrieval includes session ID."""
        session_id = "test-session-123"
        result = await retrieval_service.retrieve(
            query=sample_query,
            session_id=session_id
        )
        
        assert result["session_id"] == session_id
    
    async def test_health_check_success(self, retrieval_service):
        """Test successful health check."""
        status = await retrieval_service.health_check()
        
        assert "status" in status
        assert "components" in status
        assert status["status"] in ["healthy", "degraded", "unhealthy"]
    
    async def test_health_check_all_components(self, retrieval_service):
        """Test health check includes all components."""
        status = await retrieval_service.health_check()
        
        components = status.get("components", {})
        # Should have health info for initialized components
        assert len(components) > 0
    
    async def test_health_check_handles_errors(self):
        """Test health check handles component errors gracefully."""
        from services_version2.retrieval.core import RetrievalService, QueryProcessor, RetrievalOrchestrator
        
        # Create service with broken components
        orchestrator = RetrievalOrchestrator(
            vector_store_client=AsyncMock(health=AsyncMock(side_effect=Exception("Error"))),
            embedding_client=None,
            document_repository=None
        )
        
        service = RetrievalService(
            query_processor=QueryProcessor(),
            retrieval_orchestrator=orchestrator
        )
        
        status = await service.health_check()
        
        # Should still return a status, even if degraded
        assert "status" in status
        assert "components" in status
    
    async def test_retrieve_error_handling(self, retrieval_service):
        """Test error handling in retrieval."""
        # Make orchestrator raise exception
        retrieval_service.orchestrator.retrieve = AsyncMock(side_effect=Exception("Retrieval error"))
        
        result = await retrieval_service.retrieve(query="test query")
        
        assert result["status"] == "error"
        assert "error" in result
        assert len(result["documents"]) == 0


@pytest.mark.asyncio
class TestRetrievalServiceIntegration:
    """Integration tests for RetrievalService."""
    
    async def test_end_to_end_retrieval(self, retrieval_service):
        """Test end-to-end retrieval flow."""
        queries = [
            "HS code for cotton fabric",
            "VAT rate for imports",
            "customs duty calculation"
        ]
        
        for query in queries:
            result = await retrieval_service.retrieve(query=query, top_k=5)
            
            assert result["status"] in ["success", "invalid_query", "clarification_required"]
            assert "documents" in result
            assert "query" in result
    
    async def test_multiple_sequential_requests(self, retrieval_service):
        """Test handling multiple sequential requests."""
        for i in range(5):
            result = await retrieval_service.retrieve(
                query=f"query {i}",
                session_id=f"session-{i}"
            )
            
            assert result["query"] == f"query {i}"
            assert result["session_id"] == f"session-{i}"
