"""
Tests for Query Processing module
"""

import pytest
from services_version2.retrieval.core import QueryProcessor


class TestQueryProcessor:
    """Test QueryProcessor class."""
    
    def test_validate_valid_query(self, query_processor):
        """Test validation of valid query."""
        is_valid, error = query_processor.validate("cotton fabric")
        assert is_valid is True
        assert error is None
    
    def test_validate_empty_query(self, query_processor):
        """Test validation rejects empty query."""
        is_valid, error = query_processor.validate("")
        assert is_valid is False
        assert error is not None
    
    def test_validate_too_short(self, query_processor):
        """Test validation rejects query < 2 chars."""
        is_valid, error = query_processor.validate("a")
        assert is_valid is False
    
    def test_validate_too_long(self, query_processor):
        """Test validation rejects query > 2000 chars."""
        long_query = "a" * 2001
        is_valid, error = query_processor.validate(long_query)
        assert is_valid is False
    
    def test_normalize_text(self, query_processor):
        """Test text normalization."""
        normalized = query_processor.normalize("  Cotton   FABRIC  ")
        assert normalized == "cotton fabric"
        assert "  " not in normalized
    
    def test_expand_query_with_abbreviations(self, query_processor):
        """Test query expansion with synonyms."""
        expanded = query_processor.expand("cif value")
        assert "cost insurance freight" in expanded
    
    def test_tokenize_removes_stopwords(self, query_processor):
        """Test tokenization removes stopwords."""
        tokens = query_processor.tokenize("what is the HS code for cotton")
        assert "what" not in tokens
        assert "is" not in tokens
        assert "the" not in tokens
        assert "cotton" in tokens
        assert "code" in tokens
    
    def test_tokenize_removes_duplicates(self, query_processor):
        """Test tokenization removes duplicates."""
        tokens = query_processor.tokenize("cotton cotton fabric fabric")
        assert len(tokens) == len(set(tokens))
    
    def test_process_valid_query(self, query_processor, sample_query):
        """Test complete query processing."""
        processed = query_processor.process(sample_query)
        
        assert processed is not None
        assert processed.original == sample_query
        assert processed.normalized.lower() == processed.normalized
        assert isinstance(processed.tokens, list)
        assert len(processed.tokens) > 0
    
    def test_process_invalid_query_returns_none(self, query_processor):
        """Test processing invalid query returns None."""
        processed = query_processor.process("")
        assert processed is None
    
    def test_process_expands_query(self, query_processor):
        """Test that process expands query."""
        processed = query_processor.process("HS code lookup")
        assert len(processed.expanded) > len(processed.normalized)
    
    def test_query_with_special_chars(self, query_processor):
        """Test query with special characters."""
        processed = query_processor.process("Cotton @ $100 per kg!")
        assert processed is not None
        assert processed.original == "Cotton @ $100 per kg!"
        assert "@" not in processed.normalized or "$" not in processed.normalized


class TestProcessedQuery:
    """Test ProcessedQuery dataclass."""
    
    def test_processed_query_attributes(self, sample_processed_query):
        """Test ProcessedQuery has required attributes."""
        assert hasattr(sample_processed_query, "original")
        assert hasattr(sample_processed_query, "normalized")
        assert hasattr(sample_processed_query, "expanded")
        assert hasattr(sample_processed_query, "tokens")
    
    def test_processed_query_types(self, sample_processed_query):
        """Test ProcessedQuery attribute types."""
        assert isinstance(sample_processed_query.original, str)
        assert isinstance(sample_processed_query.normalized, str)
        assert isinstance(sample_processed_query.expanded, str)
        assert isinstance(sample_processed_query.tokens, list)
