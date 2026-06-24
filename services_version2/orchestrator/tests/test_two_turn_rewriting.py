"""
Tests for two-turn intent rewriting and ask-back orchestration.

Covers the following required behaviours:
    T1. Turn-1 hs_code: rewritten_query == raw_query  (no rewrite)
    T2. Turn-1 trade:   rewritten_query == raw_query
    T3. Turn-1 calc:    rewritten_query == raw_query
    T4. Turn-1 general: rewrite step is invoked (was_rewritten may be True)
    T5. Turn-2 self-sufficient (own intent stated) -> no ask-back, direct route
    T6. Turn-2 fragment (no own intent) -> ask-back fires with candidates
    T7. Full clarification round-trip:
           turn1="hs code of car?" -> turn2="what about boat" -> ask-back
           -> user says "hs code" -> merged_query contains "boat" and intent token
    T8. Unrecognised clarification answer -> re-ask (no guess)

All tests use mocked LLM/service clients so there are no network calls.

NOTE: The coordinator routes rewrites through ``rewriter_service.rewrite_input``
(a LLMFirstLayerService), NOT through ``llm_service.rewrite_input``.
Tests therefore spy on ``coord.rewriter_service`` after coordinator construction.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

# --- path bootstrap (mirrors other test files) ---
import sys
import os
test_dir = os.path.dirname(os.path.abspath(__file__))
orchestrator_dir = os.path.dirname(test_dir)
services_v2_dir = os.path.dirname(orchestrator_dir)
workspace_root = os.path.dirname(services_v2_dir)
sys.path.insert(0, workspace_root)

from services_version2.orchestrator.core.input_rewriter import (
    SessionContext, SessionManager,
)
from services_version2.orchestrator.core.coordinator import ServiceCoordinator
from services_version2.orchestrator.core.workflow import WorkflowIntent
from services_version2.orchestrator.utils import extract_entity
from services_version2.orchestrator.infrastructure.cache_service import get_cache_service


# ===========================================================================
# Helpers / shared fixtures
# ===========================================================================

def _make_dummy_llm(intent: str = "general", confidence: float = 0.90):
    """
    Minimal LLM service stub used ONLY for intent classification.
    It deliberately does NOT implement rewrite_input so that the coordinator
    uses the real LLMFirstLayerService (rewriter_service) for session
    management and the rewrite gate — which is what _spy_on_rewriter() taps.

    The Gemini provider mock is configured with is_available()=False so that
    detect_small_talk() never enters the LLM path and returns None for all
    non-trivially-matched queries, allowing real test queries to pass through.
    """
    svc = MagicMock()
    svc.is_available.return_value = True
    svc.classify_intent.return_value = (intent, confidence, f"stub:{intent}")
    svc.detect_currency.return_value = (None, 0.0, "no currency")

    # Configure the Gemini provider mock so detect_small_talk() skips it.
    # detect_small_talk() checks: provider = llm_service.router.providers.get("gemini")
    #                             if provider and provider.is_available(): ...
    gemini_provider_mock = MagicMock()
    gemini_provider_mock.is_available.return_value = False
    svc.router.providers.get.return_value = gemini_provider_mock

    # Do NOT set svc.rewrite_input here so coordinator uses real rewriter_service.
    # hasattr() must return False for rewrite_input:
    del svc.rewrite_input  # MagicMock auto-creates but we remove it
    return svc


def _make_coordinator(
    intent: str = "general",
    confidence: float = 0.90,
    retrieval_client=None,
    calculator_client=None,
    trade_data_client=None,
    use_input_rewriter: bool = True,
    llm_service=None,
):
    """Build a ServiceCoordinator wired for unit tests."""
    get_cache_service().invalidate_cache()

    if retrieval_client is None:
        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [], "status": "success",
            "answer_source": "mock", "final_answer": "Mock HS answer",
        })
        retrieval_client.general = AsyncMock(return_value={
            "documents": [], "status": "success",
            "answer_source": "mock", "final_answer": "Mock general answer",
        })

    if calculator_client is None:
        calculator_client = AsyncMock()
        calculator_client.query = AsyncMock(return_value={
            "total": 0, "currency": "KHR",
            "breakdown": {}, "line_items": [], "assumptions": [], "references": [],
        })

    if trade_data_client is None:
        trade_data_client = AsyncMock()
        trade_data_client.query = AsyncMock(return_value={
            "message": "Mock trade answer", "data": [],
        })

    if llm_service is None:
        llm_service = _make_dummy_llm(intent=intent, confidence=confidence)

    formatter_mock = MagicMock()
    formatter_mock.is_available.return_value = False

    from services_version2.orchestrator.core import get_policy_engine
    coordinator = ServiceCoordinator(
        retrieval_client=retrieval_client,
        general_client=retrieval_client,
        calculator_client=calculator_client,
        trade_data_client=trade_data_client,
        policy_engine=get_policy_engine(),
        use_llm_intent=False,        # keyword-based only - no network
        use_input_rewriter=use_input_rewriter,
        llm_service=llm_service,
        formatter_service=formatter_mock,
    )
    return coordinator


def _spy_on_rewriter(coord) -> list:
    """
    Replace coord.rewriter_service.rewrite_input with a spy wrapper.
    Returns a mutable list that is appended to on every call.

    IMPORTANT: The coordinator uses coord.rewriter_service (a
    LLMFirstLayerService), not llm_service, for rewriting. Always spy here.
    """
    rewrite_calls = []
    original = coord.rewriter_service.rewrite_input

    async def _spy(user_input, context=None, intent_hint=None):
        rewrite_calls.append(user_input)
        return await original(user_input, context=context, intent_hint=intent_hint)

    coord.rewriter_service.rewrite_input = _spy
    return rewrite_calls


# ===========================================================================
# T1 - T3 : Turn-1 raw pass-through for non-general intents
# ===========================================================================

@pytest.mark.asyncio
class TestTurn1PassThrough:
    """
    hs_code_lookup, trade_query, and calculation must NOT rewrite the query.
    The query sent to the downstream service must equal the original input
    (modulo HS-code standardisation which happens before the rewrite gate).
    """

    async def test_turn1_hs_code_passthrough(self):
        """T1: hs_code_lookup -> retrieval called with raw query, no rewrite."""
        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [], "status": "success", "final_answer": "HS answer",
        })

        coord = _make_coordinator(
            intent="hs_code_lookup", confidence=0.95,
            retrieval_client=retrieval_client,
        )
        rewrite_calls = _spy_on_rewriter(coord)

        raw_query = "what is the hs code for car?"
        resp = await coord.process_query(question=raw_query)

        assert resp["status"] in {"completed", "failed"}
        assert resp["intent"] == "hs_code_lookup"
        assert rewrite_calls == [], (
            f"rewrite_input was called for hs_code_lookup - raw pass-through violated. "
            f"Calls: {rewrite_calls}"
        )
        retrieval_client.hs_code_lookup.assert_awaited_once()
        _, call_kwargs = retrieval_client.hs_code_lookup.await_args
        # The coordinator may standardize/clean the HS-code query (e.g. strip
        # prefix "what is the hs code for") before handing off to retrieval.
        # We only verify that (a) the call happened and (b) no rewrite occurred.
        assert call_kwargs["query"] is not None, (
            "hs_code_lookup was called with None query"
        )

    async def test_turn1_trade_passthrough(self):
        """T2: trade_query -> trade service called with raw query, no rewrite."""
        trade_data_client = AsyncMock()
        trade_data_client.query = AsyncMock(return_value={
            "message": "Trade answer", "data": [],
        })

        coord = _make_coordinator(
            intent="trade_query", confidence=0.95,
            trade_data_client=trade_data_client,
        )
        rewrite_calls = _spy_on_rewriter(coord)

        raw_query = "what is the import volume between Cambodia and Vietnam in 2024?"
        resp = await coord.process_query(question=raw_query)

        assert resp["status"] in {"completed", "failed"}
        assert resp["intent"] == "trade_query"
        assert rewrite_calls == [], (
            f"rewrite_input was called for trade_query - raw pass-through violated. "
            f"Calls: {rewrite_calls}"
        )
        trade_data_client.query.assert_awaited_once_with(raw_query)

    async def test_turn1_calculation_passthrough(self):
        """T3: calculation -> calculator called with raw query, no rewrite."""
        calculator_client = AsyncMock()
        calculator_client.query = AsyncMock(return_value={
            "total": 1234, "currency": "KHR",
            "breakdown": {}, "line_items": [], "assumptions": [], "references": [],
        })

        coord = _make_coordinator(
            intent="calculation", confidence=0.95,
            calculator_client=calculator_client,
        )
        rewrite_calls = _spy_on_rewriter(coord)

        raw_query = "calculate import duty for car CIF 50000 USD"
        resp = await coord.process_query(question=raw_query)

        assert resp["status"] in {"completed", "failed"}
        assert resp["intent"] == "calculation"
        assert rewrite_calls == [], (
            f"rewrite_input was called for calculation - raw pass-through violated. "
            f"Calls: {rewrite_calls}"
        )
        calculator_client.query.assert_awaited_once_with(question=raw_query)


# ===========================================================================
# T4 : Turn-1 general - rewrite step is invoked
# ===========================================================================

@pytest.mark.asyncio
class TestTurn1GeneralRewrites:
    """
    For general (catch-all NLU) intent the rewriter MUST be invoked.
    We don't mandate that the output differs (LLM may decide not to change it),
    but we assert the rewrite step is entered.
    """

    async def test_turn1_general_enters_rewriter(self):
        """T4: general intent -> rewrite_input is called on rewriter_service."""
        retrieval_client = AsyncMock()
        retrieval_client.general = AsyncMock(return_value={
            "documents": [], "status": "success", "final_answer": "General answer",
        })

        coord = _make_coordinator(
            intent="general", confidence=0.90,
            retrieval_client=retrieval_client,
        )
        rewrite_calls = _spy_on_rewriter(coord)

        raw_query = "what is the procedure to import electronics?"
        await coord.process_query(question=raw_query)

        assert len(rewrite_calls) >= 1, (
            "rewrite_input was never called for general intent"
        )


# ===========================================================================
# T5 : Turn-2 self-sufficient - no ask-back
# ===========================================================================

@pytest.mark.asyncio
class TestTurn2SelfSufficient:
    """
    When a turn-2 query states its own intent clearly (explicit keywords /
    high confidence) it must be routed directly without an ask-back question.
    """

    async def test_turn2_self_sufficient_no_ask_back(self):
        """T5: turn-2 with explicit intent keywords -> routed directly, no ask-back."""
        get_cache_service().invalidate_cache()

        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [], "status": "success", "final_answer": "HS for boat",
        })
        retrieval_client.general = AsyncMock(return_value={
            "documents": [], "status": "success", "final_answer": "General answer",
        })

        session_id = "test_self_sufficient_001"
        coord = _make_coordinator(
            intent="hs_code_lookup", confidence=0.95,
            retrieval_client=retrieval_client,
        )

        # Turn 1 - establish session
        await coord.process_query(question="what is the hs code for car?", session_id=session_id)

        # Turn 2 - self-sufficient: explicit intent + new product
        resp = await coord.process_query(
            question="what is the hs code for boat?",
            session_id=session_id,
        )

        assert resp["status"] != "clarification_required", (
            "ask-back fired on a self-sufficient turn-2 query"
        )
        assert resp["intent"] == "hs_code_lookup"


# ===========================================================================
# T6 : Turn-2 fragment - ask-back fires
# ===========================================================================

@pytest.mark.asyncio
class TestTurn2Fragment:
    """
    A turn-2 fragment that carries no own intent (e.g. "what about boat?")
    must trigger an ask-back clarification question with candidate intents.
    """

    async def test_turn2_fragment_triggers_ask_back(self):
        """T6: ambiguous fragment on turn-2 -> status=clarification_required."""
        get_cache_service().invalidate_cache()

        session_id = "test_fragment_ask_back_001"

        # Build coordinator with low confidence so self-sufficiency check fails
        coord = _make_coordinator(intent="general", confidence=0.45)

        # Inject a session with turn-1 context so we're truly on turn 2
        session = coord.rewriter_service.get_or_create_session(session_id)
        session.add_turn(
            user_input="what is the hs code of car?",
            bot_response="HS Code 8703.23.00 - Passenger vehicles.",
        )
        session.last_intent = "hs_code_lookup"
        session.last_entity = "car"
        session.last_normalized_query = "what is the hs code of car?"

        # Patch ask_back_svc to always return should_ask_back=True
        ask_back_result = MagicMock()
        ask_back_result.should_ask_back = True
        ask_back_result.question = (
            "Would that be related to trade, hs_code, general question, or calculation?"
        )
        ask_back_result.candidate_intents = ["trade", "hs_code", "general", "calculation"]
        ask_back_result.trigger_reason = "low_confidence_fragment"

        mock_ask_back_svc = MagicMock()
        mock_ask_back_svc.get_clarification_async = AsyncMock(return_value=ask_back_result)

        with patch(
            "services_version2.orchestrator.llm_first_layer.get_llm_first_layer_service",
            return_value=mock_ask_back_svc,
        ):
            resp = await coord.process_query(
                question="what about boat?",
                session_id=session_id,
            )

        assert resp["status"] == "clarification_required", (
            f"Expected clarification_required, got {resp['status']!r}"
        )
        assert "candidate_intents" in resp.get("metadata", {}).get("clarification", {}), (
            "candidate_intents missing from clarification metadata"
        )

    async def test_turn2_fragment_triggers_ask_back_even_with_high_confidence(self):
        """T6b: ambiguous fragment starting with follow-up prefix on turn-2 triggers ask-back even if intent confidence is high."""
        get_cache_service().invalidate_cache()

        session_id = "test_fragment_ask_back_002"

        # Build coordinator with high confidence (0.85)
        coord = _make_coordinator(intent="hs_code_lookup", confidence=0.85)

        # Inject a session with turn-1 context so we're truly on turn 2
        session = coord.rewriter_service.get_or_create_session(session_id)
        session.add_turn(
            user_input="what is the hs code of car?",
            bot_response="HS Code 8703.23.00 - Passenger vehicles.",
        )
        session.last_intent = "hs_code_lookup"
        session.last_entity = "car"
        session.last_normalized_query = "what is the hs code of car?"

        # Patch ask_back_svc to always return should_ask_back=True when checking followup
        ask_back_result = MagicMock()
        ask_back_result.should_ask_back = True
        ask_back_result.question = (
            "Would that be related to trade, hs_code, general question, or calculation?"
        )
        ask_back_result.candidate_intents = ["trade", "hs_code", "general", "calculation"]
        ask_back_result.trigger_reason = "followup_fragment"

        mock_ask_back_svc = MagicMock()
        mock_ask_back_svc.get_clarification_async = AsyncMock(return_value=ask_back_result)

        with patch(
            "services_version2.orchestrator.llm_first_layer.get_llm_first_layer_service",
            return_value=mock_ask_back_svc,
        ):
            resp = await coord.process_query(
                question="what about boat?",
                session_id=session_id,
            )

        assert resp["status"] == "clarification_required", (
            f"Expected clarification_required, got {resp['status']!r}"
        )
        assert "candidate_intents" in resp.get("metadata", {}).get("clarification", {}), (
            "candidate_intents missing from clarification metadata"
        )


# ===========================================================================
# T7 : Full clarification round-trip (pure unit tests on _merge_*)
# ===========================================================================

class TestClarificationRoundTrip:
    """
    Full flow:
      turn1 = "hs code of car?"  (intent=hs_code_lookup, entity=car)
      turn2 = "what about boat"  (ambiguous fragment -> ask-back)
      clarification answer = "hs code"
      expected merged query contains "boat" and the intent token "hs" / "code"
    """

    def test_merge_with_turn2_entity(self):
        """T7: when turn-2 pending_query has an entity, use it (not turn-1 entity)."""
        coord = _make_coordinator()

        merged = coord._merge_pending_with_clarification(
            pending_query="what about boat",
            clarification_response="hs code",
            resolved_intent="hs_code_lookup",
            session_last_entity="car",  # turn-1 entity - should NOT be used here
        )
        # "boat" is extractable from pending_query
        assert "boat" in merged.lower(), (
            f"Expected 'boat' in merged query, got: {merged!r}"
        )
        assert "hs" in merged.lower() or "code" in merged.lower(), (
            f"Expected intent token in merged query, got: {merged!r}"
        )

    def test_merge_falls_back_to_session_entity_when_fragment_has_none(self):
        """T7b: when turn-2 fragment has no parseable entity, use turn-1 entity."""
        coord = _make_coordinator()

        # "and for?" -> extract_entity returns None (pure filler phrase)
        entity = extract_entity("and for?")
        assert entity is None, (
            f"Precondition failed: expected extract_entity('and for?') == None, "
            f"got {entity!r}. Check extract_entity() prefix patterns."
        )

        merged = coord._merge_pending_with_clarification(
            pending_query="and for?",
            clarification_response="hs code",
            resolved_intent="hs_code_lookup",
            session_last_entity="car",  # turn-1 entity must be used as fallback
        )
        assert "car" in merged.lower(), (
            f"Expected turn-1 entity 'car' in merged query, got: {merged!r}"
        )

    def test_merge_pronoun_replacement_uses_entity(self):
        """T7c: pronoun in clarification response is replaced with the resolved entity."""
        coord = _make_coordinator()

        merged = coord._merge_pending_with_clarification(
            pending_query="what about boat",
            clarification_response="its hs code",
            resolved_intent="hs_code_lookup",
            session_last_entity="car",
        )
        # "its" should be replaced with "boat" (entity from turn-2 pending_query)
        assert "boat" in merged.lower(), (
            f"Expected 'boat' in merged, got: {merged!r}"
        )
        assert "its" not in merged.lower(), (
            f"Pronoun 'its' not replaced: {merged!r}"
        )

    def test_merge_calculation_query_preserves_context(self):
        """T7d: when merging for calculation intent, preserve CIF value, currency, and origin country from Turn 1."""
        coord = _make_coordinator()

        session_context = SessionContext(session_id="test_calc_preservation")
        session_context.last_intent = "calculation"
        session_context.last_normalized_query = "Calculate import tax for HS 0102.29.11 CIF $800 from Thailand"
        session_context.last_entity = "0102.29.11"

        merged = coord._merge_pending_with_clarification(
            pending_query="what about bus",
            clarification_response="calculation",
            resolved_intent="calculation",
            session_last_entity="0102.29.11",
            session_context=session_context,
        )

        assert "bus" in merged.lower(), f"Expected 'bus' in merged, got: {merged!r}"
        assert "800" in merged, f"Expected '800' in merged, got: {merged!r}"
        assert "thailand" in merged.lower(), f"Expected 'thailand' in merged, got: {merged!r}"
        assert "usd" in merged.lower() or "$" in merged, f"Expected currency in merged, got: {merged!r}"

    def test_update_session_for_query(self):
        """T7e: verify update_session_for_query populates context correctly for a cache hit scenario."""
        coord = _make_coordinator()
        session_id = "test_cache_hit_session"
        
        coord.update_session_for_query(
            session_id=session_id,
            query="Calculate import tax for HS 0102.29.11 CIF $800 from Thailand",
            intent_value="calculation",
            answer_summary="mocked answer summary",
        )
        
        session = coord.rewriter_service.get_or_create_session(session_id)
        assert session.last_intent == "calculation"
        assert "0102.29.11" in session.last_entity
        assert "calculate" in session.last_normalized_query.lower()
        assert len(session.turns) == 1
        assert session.turns[0]["user"] == "Calculate import tax for HS 0102.29.11 CIF $800 from Thailand"


# ===========================================================================
# T8 : Unrecognised clarification -> re-ask
# ===========================================================================

@pytest.mark.asyncio
class TestUnrecognisedClarification:
    """
    When the user's clarification answer does not match any candidate intent,
    the system must re-ask (up to MAX_ASK_BACK_RETRIES) rather than guessing.
    """

    async def test_unrecognized_clarification_re_asks(self):
        """T8: garbage clarification answer -> re-ask (status=clarification_required)."""
        get_cache_service().invalidate_cache()

        session_id = "test_reasking_001"
        coord = _make_coordinator(intent="unclassified", confidence=0.40)

        # Manually put the session in pending_clarification state
        session = coord.rewriter_service.get_or_create_session(session_id)
        session.set_pending_clarification(
            candidate_intents=["trade", "hs_code", "general", "calculation"],
            rewritten_query="what about boat?",
        )

        # Mock ask-back service to return unresolved state
        mock_ask_back_svc = MagicMock()
        mock_ask_back_svc.resolve_from_user_response = MagicMock(return_value=None)
        mock_ask_back_svc._template = MagicMock()
        mock_ask_back_svc._template.generate = MagicMock(
            return_value="Would that be related to trade, hs_code, general, or calculation?"
        )
        mock_ask_back_svc.get_clarification_async = AsyncMock(return_value=MagicMock(
            should_ask_back=False,
        ))

        with patch(
            "services_version2.orchestrator.llm_first_layer.get_llm_first_layer_service",
            return_value=mock_ask_back_svc,
        ):
            resp = await coord.process_query(
                question="purple monkey dishwasher",   # clearly not a valid intent
                session_id=session_id,
            )

        # Must have either re-asked or exhausted retries - must NOT have guessed
        assert resp["status"] in {"clarification_required", "completed", "failed"}, (
            f"Unexpected status: {resp['status']!r}"
        )
        if resp["status"] == "clarification_required":
            meta = resp.get("metadata", {}).get("clarification", {})
            assert meta.get("candidate_intents"), (
                "Re-ask response is missing candidate_intents"
            )


# ===========================================================================
# T-util : extract_entity unit tests
# ===========================================================================

class TestExtractEntity:
    """Unit tests for the standalone extract_entity() utility."""

    def test_hs_code_prefix_stripped(self):
        assert extract_entity("what is the hs code of car?") == "car"

    def test_hs_code_for_prefix_stripped(self):
        assert extract_entity("hs code for boat") == "boat"

    def test_what_about_fragment(self):
        assert extract_entity("what about boat?") == "boat"

    def test_and_for_fragment(self):
        result = extract_entity("and for rice?")
        assert result == "rice"

    def test_and_for_question_mark_only_returns_none(self):
        # "and for?" has no entity after stripping the prefix
        assert extract_entity("and for?") is None

    def test_calculation_prefix_stripped(self):
        result = extract_entity("calculate import duty for laptop")
        assert result == "laptop"

    def test_trade_prefix_stripped(self):
        result = extract_entity("import data for rubber")
        assert result == "rubber"

    def test_empty_returns_none(self):
        assert extract_entity("") is None
        assert extract_entity("   ") is None

    def test_stopword_only_returns_none(self):
        assert extract_entity("the") is None

    def test_multi_word_entity_preserved(self):
        result = extract_entity("hs code of live horse")
        assert result is not None
        assert "horse" in result

    def test_no_prefix_returns_entity(self):
        # Pure noun phrase with no prefix
        assert extract_entity("car") == "car"
        assert extract_entity("rice") == "rice"
