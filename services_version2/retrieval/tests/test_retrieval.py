"""
Tests for Retrieval Orchestration module
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
class TestRetrievalOrchestrator:
    """Test RetrievalOrchestrator class."""
    
    async def test_retrieve_semantic_search(self, retrieval_orchestrator, sample_processed_query):
        """Test semantic search retrieval."""
        results = await retrieval_orchestrator.retrieve_semantic(
            query=sample_processed_query.expanded,
            top_k=10
        )
        
        assert isinstance(results, list)
        assert len(results) > 0
        assert "id" in results[0]
        assert "score" in results[0]
    
    async def test_retrieve_structured_search(self, retrieval_orchestrator, sample_processed_query):
        """Test structured search retrieval."""
        results = await retrieval_orchestrator.retrieve_structured(
            query=sample_processed_query.normalized,
            query_tokens=sample_processed_query.tokens
        )
        
        assert isinstance(results, list)
    
    async def test_retrieve_combined(self, retrieval_orchestrator, sample_processed_query):
        """Test combined retrieval."""
        result = await retrieval_orchestrator.retrieve(
            processed_query=sample_processed_query,
            top_k=10,
            use_semantic=True,
            use_structured=True
        )
        
        assert "query" in result
        assert "documents" in result
        assert "total_count" in result
        assert result["query"] == sample_processed_query.original
    
    async def test_retrieve_semantic_only(self, retrieval_orchestrator, sample_processed_query):
        """Test retrieval with semantic search only."""
        result = await retrieval_orchestrator.retrieve(
            processed_query=sample_processed_query,
            top_k=10,
            use_semantic=True,
            use_structured=False
        )
        
        assert "documents" in result
        assert "semantic_count" in result
    
    async def test_retrieve_structured_only(self, retrieval_orchestrator, sample_processed_query):
        """Test retrieval with structured search only."""
        result = await retrieval_orchestrator.retrieve(
            processed_query=sample_processed_query,
            top_k=10,
            use_semantic=False,
            use_structured=True
        )
        
        assert "documents" in result
        assert "structured_count" in result
    
    async def test_retrieve_respects_top_k(self, retrieval_orchestrator, sample_processed_query):
        """Test that retrieval respects top_k limit."""
        result = await retrieval_orchestrator.retrieve(
            processed_query=sample_processed_query,
            top_k=5
        )
        
        assert len(result["documents"]) <= 5
    
    async def test_retrieve_deduplicates_results(self, retrieval_orchestrator, sample_processed_query):
        """Test that retrieval deduplicates results."""
        result = await retrieval_orchestrator.retrieve(
            processed_query=sample_processed_query,
            top_k=20
        )
        
        doc_ids = [d.get("id") for d in result["documents"]]
        assert len(doc_ids) == len(set(doc_ids))
    
    async def test_retrieve_handles_missing_clients(self):
        """Test retrieval with missing clients."""
        from services_version2.retrieval.core import RetrievalOrchestrator
        
        orchestrator = RetrievalOrchestrator(
            vector_store_client=None,
            embedding_client=None,
            document_repository=None
        )
        
        processed = MagicMock()
        processed.original = "test"
        processed.normalized = "test"
        processed.expanded = "test"
        processed.tokens = ["test"]
        
        result = await orchestrator.retrieve(processed, use_semantic=True, use_structured=True)
        assert "error" in result or len(result.get("documents", [])) == 0
    
    async def test_retrieve_error_handling(self, retrieval_orchestrator, sample_processed_query):
        """Test error handling in retrieval."""
        # Make vector store raise exception
        retrieval_orchestrator.vector_store.search = AsyncMock(side_effect=Exception("Connection error"))
        
        result = await retrieval_orchestrator.retrieve(
            processed_query=sample_processed_query,
            use_semantic=True,
            use_structured=False
        )
        
        # Should handle error gracefully
        assert "documents" in result
        assert isinstance(result["documents"], list)
