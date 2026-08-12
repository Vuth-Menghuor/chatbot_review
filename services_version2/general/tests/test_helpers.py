"""
Unit tests for the pure / lexical logic in the General Retrieval Service.

These tests do **not** touch Qdrant, Redis, or Gemini — they exercise the
query processing, language detection, trade-data detection, and reranking
helpers directly, which is where most of the actual classification behaviour
lives.

Run with::

    pytest tests/test_helpers.py -v
"""

import pytest
from unittest.mock import MagicMock

from app.rag.query import QueryProcessor, ProcessedQuery
from app.utils.language_utils import detect_language, normalize_by_language, expand_by_language
from app.rag.service import GeneralRetrievalService


# =========================================================================
# Language Detection
# =========================================================================


class TestLanguageDetection:
    """Khmer (km) vs English (en) detection."""

    def test_english_default(self):
        """Plain English text → 'en'."""
        assert detect_language("What documents do I need to import?") == "en"

    def test_khmer_detected(self):
        """Khmer Unicode characters → 'km'."""
        assert detect_language("តើខ្ញុំត្រូវការឯកសារអ្វីខ្លះដើម្បីនាំចូល?") == "km"

    def test_mixed_khmer_english(self):
        """Any Khmer character present → 'km'."""
        assert detect_language("I need ពន្ធ information") == "km"

    def test_empty_string(self):
        """Empty string → 'en'."""
        assert detect_language("") == "en"

    def test_none_input(self):
        """None input → 'en'."""
        assert detect_language(None) == "en"


# =========================================================================
# Normalization
# =========================================================================


class TestNormalization:
    """Text normalisation and language-aware expansion."""

    def test_lowercase_and_whitespace(self):
        """Collapses multiple whitespace into single spaces and lowercases."""
        text, lang = normalize_by_language("  What   Documents  ")
        assert text == "what documents"
        assert lang == "en"

    def test_khmer_expansion_appends_english_hints(self):
        """Khmer customs terms get English hints appended."""
        result = expand_by_language("ពន្ធគយនាំចូល", "km")
        assert "tax duty" in result
        assert "customs" in result
        assert "import" in result

    def test_english_no_expansion(self):
        """English text is returned as-is (no expansion)."""
        result = expand_by_language("customs import procedures", "en")
        assert result == "customs import procedures"


# =========================================================================
# Query Processing
# =========================================================================


class TestQueryProcessor:
    """Full query processing pipeline."""

    def setup_method(self):
        self.processor = QueryProcessor()

    def test_validation_rejects_empty(self):
        """Empty query → invalid."""
        valid, error = self.processor.validate("")
        assert not valid
        assert error is not None

    def test_validation_rejects_too_short(self):
        """Single character → invalid."""
        valid, error = self.processor.validate("a")
        assert not valid

    def test_validation_accepts_valid(self):
        """Normal query → valid."""
        valid, error = self.processor.validate("import procedures")
        assert valid
        assert error is None

    def test_normalization_removes_special_chars(self):
        """Special characters stripped; alphanumerics kept."""
        normalized = self.processor.normalize("Hello! How are you? @#$")
        assert "!" not in normalized
        assert "@" not in normalized
        assert "hello" in normalized

    def test_expansion_adds_abbreviation_meanings(self):
        """CIF → cost insurance freight customs valuation."""
        expanded = self.processor.expand("what is cif")
        assert "cost insurance freight" in expanded

    def test_tokenize_removes_stopwords(self):
        """Common English stopwords are stripped."""
        tokens = self.processor.tokenize("what is the procedure for import")
        assert "what" not in tokens
        assert "is" not in tokens
        assert "the" not in tokens
        assert "import" in tokens

    def test_tokenize_returns_unique(self):
        """Duplicate tokens are deduplicated."""
        tokens = self.processor.tokenize("import import import procedure")
        assert len([t for t in tokens if t == "import"]) == 1

    def test_full_process_returns_processed_query(self):
        """Happy path — returns a ProcessedQuery with all fields populated."""
        result = self.processor.process("What is the CIF value for imports?")
        assert result is not None
        assert isinstance(result, ProcessedQuery)
        assert result.original == "What is the CIF value for imports?"
        assert len(result.tokens) > 0
        assert result.language == "en"

    def test_invalid_query_returns_none(self):
        """Invalid query → None (not an exception)."""
        result = self.processor.process("")
        assert result is None


# =========================================================================
# Trade Data Detection
# =========================================================================


class TestTradeDataDetection:
    """Detection of trade-data analytics queries requiring a time period."""

    def test_import_statistics_triggers(self):
        """'import statistics' → trade data query."""
        assert GeneralRetrievalService._is_trade_data_query("import statistics 2024") is True

    def test_trade_volume_triggers(self):
        """'trade volume' → trade data query."""
        assert GeneralRetrievalService._is_trade_data_query("trade volume by country") is True

    def test_procedural_import_no_triggers(self):
        """'How do I import goods' is procedural, not analytics → False."""
        assert GeneralRetrievalService._is_trade_data_query("How do I import goods?") is False

    def test_single_dimension_no_triggers(self):
        """'import' alone without analytics term → False."""
        assert GeneralRetrievalService._is_trade_data_query("import") is False

    def test_has_time_period_detects_year(self):
        """'2024' → has time period."""
        assert GeneralRetrievalService._has_time_period("trade volume 2024") is True

    def test_has_time_period_detects_quarter(self):
        """'Q1' → has time period."""
        assert GeneralRetrievalService._has_time_period("export data Q1 2024") is True

    def test_has_time_period_detects_month(self):
        """'January' → has time period."""
        assert GeneralRetrievalService._has_time_period("import data January 2024") is True

    def test_no_time_period(self):
        """No date/quarter/month → no time period."""
        assert GeneralRetrievalService._has_time_period("trade statistics by country") is False


# =========================================================================
# Reranking
# =========================================================================


class TestReranking:
    """Lexical reranking of general documents."""

    @staticmethod
    def make_doc(content, score=0.5, metadata=None):
        return {
            "id": "doc-1",
            "content": content,
            "score": score,
            "metadata": metadata or {},
        }

    @staticmethod
    def _make_service():
        """Create a GeneralRetrievalService with mock dependencies for reranking."""
        return GeneralRetrievalService(
            query_processor=MagicMock(),
            retrieval_orchestrator=MagicMock(),
            config=MagicMock(),
        )

    def test_exact_phrase_boost(self):
        """Documents containing the exact query phrase score higher."""
        query = "customs declaration form"
        good = self.make_doc("You need a customs declaration form to import goods.")
        bad = self.make_doc("Customs procedures vary by country.")
        docs = [bad, good]
        svc = self._make_service()
        reranked = svc._rerank_general_documents_by_query(query, docs)
        assert reranked[0]["score"] > reranked[1]["score"]

    def test_empty_docs_returns_empty(self):
        """No documents → empty list."""
        svc = self._make_service()
        result = svc._rerank_general_documents_by_query("query", [])
        assert result == []

    def test_metadata_heavy_chunk_penalized(self):
        """Frontmatter/metadata chunks score lower than content chunks."""
        query = "import procedures"
        metadata_doc = self.make_doc(
            "doc_id: abc123 title: Import Guide effective_date: 2024-01-01",
            score=0.5,
            metadata={"chunk_idx": 0},
        )
        content_doc = self.make_doc(
            "To import goods into Cambodia you must file a customs declaration.",
            score=0.5,
            metadata={"chunk_idx": 1},
        )
        svc = self._make_service()
        reranked = svc._rerank_general_documents_by_query(
            query, [metadata_doc, content_doc]
        )
        # Content doc should rank higher despite same base score.
        assert reranked[0]["id"] == content_doc["id"]
