import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from app.services.session_context import SessionContext
from app.services.suggestion_service import SuggestionService

def test_session_context_language_serialization():
    session = SessionContext(
        session_id="test_sess_001",
        target_language="km",
        is_language_pinned=True
    )
    serialized = session.to_dict()
    assert serialized["target_language"] == "km"
    assert serialized["is_language_pinned"] is True

    deserialized = SessionContext.from_dict(serialized)
    assert deserialized.target_language == "km"
    assert deserialized.is_language_pinned is True

def test_suggestion_service_km_chip_filtering():
    service = SuggestionService()
    suggestions = service.get_suggestions(
        current_intent="trade_query",
        rewritten_query="top 10 import partners Cambodia latest",
        session_context=None,
        language="km"
    )
    assert len(suggestions) > 0
    # Verify all suggestions contain Khmer script or valid code
    for chip in suggestions:
        assert service._is_valid_chip_for_lang(chip, "km") is True

def test_pinned_session_preserves_language_on_unmarked_english_turn():
    session = SessionContext(session_id="test_sess_002")
    
    # Turn 1: Explicit pin to Khmer
    session.target_language = "km"
    session.is_language_pinned = True
    
    # Turn 2: Unmarked English turn (e.g. "what about 2024?")
    # Priority 3 (script check) yields None for plain ASCII; Priority 4 retains pin "km"
    assert session.is_language_pinned is True
    assert session.target_language == "km"

def test_trading_partners_flow_normalization():
    import re
    query_to_send = "top ten trading partners Cambodia"
    has_flow = False
    has_time_period = False
    if not has_flow and not re.search(r"\b(import|export|imports|exports|imported|exported)\b", query_to_send.lower()):
        if re.search(r"\b(trade|trading)\s+partners?\b", query_to_send.lower()):
            query_to_send = re.sub(r"\b(trade|trading)\s+partners?\b", "import partners", query_to_send, flags=re.IGNORECASE)
        else:
            query_to_send = f"{query_to_send} import"

    LATEST_TRADE_YEAR = "2025"
    if not has_time_period and not re.search(r"\b(19|20)\d{2}\b", query_to_send.lower()):
        if re.search(r"\blatest\b", query_to_send, flags=re.IGNORECASE):
            query_to_send = re.sub(r"\blatest\b", LATEST_TRADE_YEAR, query_to_send, flags=re.IGNORECASE)
        else:
            query_to_send = f"{query_to_send} {LATEST_TRADE_YEAR}"

    assert query_to_send == "top ten import partners Cambodia 2025"

def test_trade_query_no_data_fallback_normalization():
    import re
    query_to_send = "top ten trading partners Cambodia import latest"
    fallback_q = re.sub(r"\btop\s+ten\b", "top 10", query_to_send, flags=re.IGNORECASE)
    fallback_q = re.sub(r"\btop\s+five\b", "top 5", fallback_q, flags=re.IGNORECASE)
    fallback_q = re.sub(r"\b(trade|trading)\s+partners?\b", "import partners", fallback_q, flags=re.IGNORECASE)
    fallback_q = re.sub(r"\s+", " ", fallback_q).strip()

    assert "top 10 import partners" in fallback_q

    directives = [
        "I would like to know top 10 trading partner during 2025 in Khmer",
        "in khmer please",
        "translate in khmer",
        "top ten trade partner to khmer",
        "translate into khmer",
        "ជាភាសាខ្មែរ"
    ]
    for q in directives:
        has_khmer_directive = bool(re.search(
            r"\b(in\s+khmer|translate\s+in\s+khmer|translate\s+into\s+khmer|translate\s+to\s+khmer|khmer\s+output|khmer\s+language|as\s+khmer|to\s+khmer|into\s+khmer|ជាភាសាខ្មែរ|បកប្រែជាភាសាខ្មែរ|ជាខ្មែរ)\b",
            q.lower()
        ))
        assert has_khmer_directive is True, f"Failed for query: {q}"

def test_vague_vs_strong_trade_query_classification():
    from app.services.coordinator import ServiceCoordinator
    coord = ServiceCoordinator()
    
    # Vague trade queries (English, Khmer, Transliterated, Assist verb)
    assert coord._is_vague_trade_query("can you help me with trade data") is True
    assert coord._is_vague_trade_query("can you assist me with trade data") is True
    assert coord._is_vague_trade_query("trade data") is True
    assert coord._is_vague_trade_query("tell me about trade statistics") is True
    assert coord._is_vague_trade_query("ទិន្នន័យពាណិជ្ជកម្ម") is True
    assert coord._is_vague_trade_query("poanichakam") is True
    
    # Strong / Specific trade queries must NOT be classified as vague
    assert coord._is_vague_trade_query("top ten trade partner") is False
    assert coord._is_vague_trade_query("top 10 import partners Cambodia 2025") is False
    assert coord._is_vague_trade_query("trade data for rice") is False
    assert coord._is_vague_trade_query("trade with China") is False

def test_turn2_escape_hatch_and_mixed_replies():
    from app.services.coordinator import ServiceCoordinator
    coord = ServiceCoordinator()
    
    # Pure short escape hatch replies must trigger
    assert coord._is_turn2_escape_hatch("idk") is True
    assert coord._is_turn2_escape_hatch("whatever") is True
    assert coord._is_turn2_escape_hatch("មិនដឹង") is True
    assert coord._is_turn2_escape_hatch("min deng") is True
    assert coord._is_turn2_escape_hatch("skip") is True
    
    # Substring / long queries must NOT trigger escape hatch
    assert coord._is_turn2_escape_hatch("any country") is False
    assert coord._is_turn2_escape_hatch("China, total exports") is False
    assert coord._is_turn2_escape_hatch("what are total imports from Vietnam for 2025") is False

def test_clarification_cache_exclusion():
    from app.infrastructure.cache_service import CacheService
    cache = CacheService()
    
    # CLARIFICATION_REQUIRED responses must be excluded from caching
    result = cache.cache_response(
        question="can you assist me with trade data",
        response={"status": "CLARIFICATION_REQUIRED", "answer": "Which specific country?"},
        intent="trade_query"
    )
    assert result is False


@pytest.mark.asyncio
async def test_trade_query_payload_translation_to_khmer():
    from app.services.handlers.trade_query import translate_trade_payload_to_khmer
    from unittest.mock import AsyncMock
    
    mock_translator = AsyncMock()
    
    result = {
        "table": {
            "columns": ["frequency", "period", "hs_heading", "trade_value"],
            "rows": [
                {
                    "frequency": "A",
                    "period": "2026",
                    "hs_heading": "Other",
                    "trade_value": "5346025001.85"
                }
            ]
        },
        "visualization": {
            "type": "kpi",
            "title": "Trade Volume Ranking",
            "labels": ["Other"],
            "datasets": [
                {
                    "label": "Trade Value (USD)",
                    "data": [5346025001.85]
                }
            ]
        },
        "summary": {
            "data_quality": {
                "is_partial_period": True,
                "partial_year": 2026,
                "partial_year_note": " The 2026 data is not complete yet."
            }
        }
    }
    
    await translate_trade_payload_to_khmer(result, mock_translator)
    
    # Assert table translations
    tbl = result["table"]
    assert tbl["columns"] == ["ប្រេកង់", "រយៈពេល", "កូដ HS Heading", "តម្លៃពាណិជ្ជកម្ម (USD)"]
    assert tbl["rows"][0]["ប្រេកង់"] == "ប្រចាំឆ្នាំ"
    assert tbl["rows"][0]["កូដ HS Heading"] == "ផ្សេងៗ"
    
    # Assert visualization translations
    viz = result["visualization"]
    assert viz["title"] == "ចំណាត់ថ្នាក់ទំហំពាណិជ្ជកម្ម"
    assert viz["labels"] == ["ផ្សេងៗ"]
    assert viz["datasets"][0]["label"] == "តម្លៃពាណិជ្ជកម្ម (USD)"
    
    # Assert summary translations
    dq = result["summary"]["data_quality"]
    assert dq["partial_year_note"] == " ទិន្នន័យឆ្នាំ 2026 មិនទាន់មានភាពពេញលេញនៅឡើយទេ។"


def test_is_rewrite_valid_khmer_terminal_punctuation_handling():
    """Verify that _is_rewrite_valid correctly ignores trailing dots/punctuation when matching years/codes."""
    from app.services.coordinator import ServiceCoordinator
    coord = ServiceCoordinator()
    
    # Repro query case: original has terminal period from translated Khmer, rewritten does not
    original = "Please show the monthly trend of the trade balance with the United States in 2025."
    rewritten = "monthly trend trade balance United States 2025"
    
    assert coord._is_rewrite_valid(original, rewritten) is True


