"""
test_few_shot_llm_eval.py
--------------------------
Live-LLM evaluation tests for the 9 few-shot examples in gemini_unified_first_layer.

These tests call the REAL Gemini API and are therefore:
  - Non-deterministic (confidence values vary per run)
  - Network-dependent / cost-incurring
  - Excluded from standard CI runs via: pytest -m "not llm_eval"

Run manually or in nightly eval pipelines:
    pytest tests/eval/test_few_shot_llm_eval.py -v -m llm_eval

Requirements:
  - GEMINI_API_KEY env variable set
  - Orchestrator services running (or at least the AI layer importable)
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest

# ---------------------------------------------------------------------------
# Skip entire module if no API key is available
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.llm_eval

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    pytest.skip(
        "GEMINI_API_KEY not set — skipping live LLM eval tests",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Parametrised live-LLM eval cases
# ---------------------------------------------------------------------------

FEW_SHOT_EVAL_CASES = [
    # (test_id, query, expected_intent, min_confidence)
    ("comparative_costly",    "but which one more costly??",            "general",        0.85),
    ("comparative_cbu_ckd",   "is CBU or CKD better for importing?",   "general",        0.85),
    ("bare_commodity_rice",   "rice",                                    "hs_code_lookup", 0.90),
    ("bare_commodity_bmw",    "BMW M8",                                  "hs_code_lookup", 0.90),
    ("trade_stats_query",     "Cambodia imports from Vietnam in 2024",  "trade_query",    0.90),
    ("capability_check_duty", "can you help me calculate import duty?", "calculation",    0.40),
    ("greeting_hello",        "hello",                                   "small_talk",     0.90),
    ("doc_followup",          "what documents do I need for that?",     "general",        0.85),
    ("tariff_followup",       "what is the tariff code for it?",        "hs_code_lookup", 0.85),
]


@pytest.mark.llm_eval
@pytest.mark.asyncio
@pytest.mark.parametrize("test_id,query,expected_intent,min_conf", FEW_SHOT_EVAL_CASES)
async def test_gemini_classifies_few_shot_intent(test_id, query, expected_intent, min_conf):
    """
    Calls the real Gemini unified_first_layer_call and asserts:
      1. The returned intent matches the expected value.
      2. The returned confidence meets the minimum threshold.

    NOTE: Confidence thresholds here are loose (0.85 for most, 0.40 for
    capability checks which are intentionally ambiguous). The test will
    not fail on slight confidence drift — only on wrong intent classification.
    """
    from app.ai import get_llm_first_layer_service
    service = get_llm_first_layer_service()

    result = await service.get_unified_result(query, session_context=None)

    assert result, f"[{test_id}] get_unified_result returned empty for query '{query}'"
    assert "intent" in result, f"[{test_id}] 'intent' key missing from result: {result}"
    assert "confidence" in result, f"[{test_id}] 'confidence' key missing from result: {result}"

    actual_intent = result["intent"]
    actual_confidence = result["confidence"]

    assert actual_intent == expected_intent, (
        f"[{test_id}] Gemini classified '{query}' as '{actual_intent}' "
        f"but expected '{expected_intent}'. Full result: {result}"
    )
    assert actual_confidence >= min_conf, (
        f"[{test_id}] Confidence {actual_confidence:.2f} < {min_conf} "
        f"for query '{query}' (intent: {actual_intent})"
    )
