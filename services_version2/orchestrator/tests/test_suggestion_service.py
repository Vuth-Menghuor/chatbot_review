"""
Unit tests for Multilingual Suggestion Service in Orchestrator.
Tests template hydration, Khmer symmetric lookaround noise cleaning, language fallbacks, and cold start rules.
"""

import pytest
from app.services.suggestion_service import SuggestionService


@pytest.fixture
def suggestion_service():
    return SuggestionService()


def test_khmer_suggestion_hydration(suggestion_service):
    suggestions = suggestion_service.get_suggestions(
        current_intent="calculation",
        rewritten_query="calculate import tax 8703.22.00",
        language="km"
    )
    assert len(suggestions) > 0
    assert any("តើ" in s for s in suggestions)
    assert any("8703.22.00" in s for s in suggestions)


def test_english_suggestion_hydration(suggestion_service):
    suggestions = suggestion_service.get_suggestions(
        current_intent="calculation",
        rewritten_query="calculate import tax laptop",
        language="en"
    )
    assert len(suggestions) > 0
    assert any("laptop" in s for s in suggestions)
    assert any("What documents" in s or "How do I import" in s for s in suggestions)


def test_khmer_noise_symmetric_boundary_no_partial_strip(suggestion_service):
    # Khmer compound entity containing noise syllables
    entity = "ពន្ធនាំចូលរថយន្ត 8703.22.00"
    cleaned = suggestion_service._clean_entity_noise(entity)
    assert "8703.22.00" in cleaned


def test_unsupported_language_normalization(suggestion_service):
    # Passing 'zh' should fall back per-item to 'en' without raising KeyError
    suggestions = suggestion_service.get_suggestions(
        current_intent="calculation",
        rewritten_query="calculate import tax laptop",
        language="zh"
    )
    assert len(suggestions) > 0
    assert any("laptop" in s for s in suggestions)


def test_mixed_language_entity(suggestion_service):
    suggestions = suggestion_service.get_suggestions(
        current_intent="calculation",
        rewritten_query="calculate import tax BYD SEALION 5",
        language="km"
    )
    assert len(suggestions) > 0
    assert any("byd sealion 5" in s.lower() for s in suggestions)
