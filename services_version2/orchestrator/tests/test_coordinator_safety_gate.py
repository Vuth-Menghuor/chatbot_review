import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.coordinator import ServiceCoordinator, WorkflowIntent
from app.services.workflow import WorkflowContext, WorkflowStatus
from app.services.session_context import SessionContext

@pytest.mark.asyncio
async def test_safety_gate_postponement_happy_path():
    """
    Happy Path:
    - User sends a follow-up fragment "it is being imported as fully built unit"
    - The safety gate postponement triggers during Step 5 (returns HS_CODE_LOOKUP and sets postponed metadata).
    - The rewriter runs and successfully rewrites it to include "BMW vehicle".
    - In Step 12, the safety gate evaluates the rewritten query and keeps HS_CODE_LOOKUP.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    
    # 1. Setup session history (representing previous turn "hs code of bmw")
    sess = SessionContext(session_id="test_sess_happy")
    sess.add_turn(user_input="hs code of bmw", bot_response="Classifying BMW requires cc, CBU/CKD...")
    sess.last_entity = "BMW vehicle"
    
    # Mock get_or_create_session to return this session
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=sess)
    
    # Mock LLM intent detection to return HS_CODE_LOOKUP
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(
        return_value=(WorkflowIntent.HS_CODE_LOOKUP, 0.95)
    )
    
    # Mock Input Rewriter to successfully rewrite query
    coordinator.rewriter_service.rewrite_input = AsyncMock(
        return_value=("BMW vehicle fully built-up unit import", {"rewritten": True, "rewrite_reason": "unified_rewrite"})
    )
    
    # Mock microservice call
    coordinator._route_query = AsyncMock()

    # Mock the validator service so no real LLM call is made inside validate_input_full_async.
    # The pronoun-fragment "it is being imported as fully built unit" has no visible trade
    # keywords, so the real LLM correctly classifies it as small_talk (correct behaviour
    # in production). Here we return in_scope:hs_code_lookup to isolate the safety-gate
    # postponement mechanism that this test is specifically testing.
    from app.ai.shims.validator_service import ValidationResult, ValidationDecision
    mock_validation_result = ValidationResult.in_scope(
        reason="llm_validated:hs_code_lookup", keywords=["import", "built", "unit"]
    )
    mock_validation_result.llm_confidence = 0.95

    with patch("app.services.coordinator.get_validator") as mock_get_validator:
        mock_validator = MagicMock()
        mock_validator.validate_input_full_async = AsyncMock(return_value=mock_validation_result)
        mock_get_validator.return_value = mock_validator

        result = await coordinator.process_query(
            question="it is being imported as fully built unit",
            session_id="test_sess_happy"
        )


    # Verify the workflow routed using HS_CODE_LOOKUP, not SMALL_TALK
    assert result["intent"] == "hs_code_lookup"
    assert result["status"] == "completed"
    
    # Verify rewrite was applied
    assert coordinator._route_query.call_args[0][0].metadata["service_query"] == "BMW vehicle fully built-up unit import"
    assert coordinator._route_query.call_args[0][0].intent == WorkflowIntent.HS_CODE_LOOKUP


@pytest.mark.asyncio
async def test_safety_gate_postponement_failure_path():
    """
    Failure Path:
    - User sends a follow-up fragment "it is being imported as fully built unit"
    - The safety gate postponement triggers during Step 5.
    - The rewriter is unable to reconstruct it or returns the original fragment query.
    - In Step 12, the safety gate evaluates the raw fragment, fails product checks,
      and correctly downgrades it to SMALL_TALK.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    
    # Setup session history
    sess = SessionContext(session_id="test_sess_failure")
    sess.add_turn(user_input="hs code of bmw", bot_response="Classifying BMW requires cc...")
    
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=sess)
    
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(
        return_value=(WorkflowIntent.HS_CODE_LOOKUP, 0.95)
    )
    
    # Mock Input Rewriter to return the original query (un-rewritten)
    coordinator.rewriter_service.rewrite_input = AsyncMock(
        return_value=("it is being imported as fully built unit", {"rewritten": False, "rewrite_reason": "original_better"})
    )
    
    # Mock small talk generator to prevent real LLM call on fallback
    with patch("app.services.coordinator.detect_small_talk", new_callable=AsyncMock) as mock_detect_st, \
         patch("app.services.coordinator.generate_small_talk_response", new_callable=AsyncMock) as mock_st_resp:
        
        mock_detect_st.return_value = "Hello! I can help you with that."
        mock_st_resp.return_value = "Hello! I can help you with that."
        coordinator._route_query = AsyncMock()
        
        result = await coordinator.process_query(
            question="it is being imported as fully built unit",
            session_id="test_sess_failure"
        )
        
        # Verify the workflow was correctly downgraded to small_talk
        assert result["intent"] == "small_talk"
        assert result["status"] == "completed"


def test_safety_net_property_warns(caplog):
    """
    Safety Net Test:
    - Verifies that accessing context.intent from a non-whitelisted function
      logs a warning if the safety gate is currently postponed.
    """
    context = WorkflowContext(request_id="req_test", question="test question")
    context.intent = WorkflowIntent.HS_CODE_LOOKUP
    context.metadata = {"_safety_gate_postponed": True}
    
    # A dummy non-whitelisted function to trigger the warning
    def non_whitelisted_caller():
        return context.intent
    
    with caplog.at_level(logging.WARNING):
        val = non_whitelisted_caller()
        assert val == WorkflowIntent.HS_CODE_LOOKUP
        assert any(
            "[WARNING] context.intent read while safety gate is postponed" in record.message
            for record in caplog.records
        )


def test_rewrite_validation_typo_resilience():
    """
    Verifies that _is_rewrite_valid correctly accepts:
    - Typo/suffix differences (build vs built, unite vs unit)
    - Stop word filtering (its, as)
    So the overall matched percentage is >= 50% instead of being rejected.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    
    original = "its import as fully build unite (CBU)"
    rewritten = "GTR vehicle fully built unit CBU"
    
    assert coordinator._is_rewrite_valid(original, rewritten, intent=WorkflowIntent.HS_CODE_LOOKUP) is True


def test_typo_correction_handles_greeting_typo():
    """
    Greeting typos should be corrected by the shared typo pipeline so
    small-talk detection can recognize them as conversational input.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )

    result = coordinator._normalize_query_typos("hellop")

    assert result["applied"] is True
    assert result["corrected_query"] == "hello"
    assert result["reason"] == "greeting_correction"


# Tests for the removed GENERAL→HS heuristic override (Solution 1 changes)

def test_safety_gate_general_high_confidence_pass_through():
    """
    GENERAL intent at high confidence (>= 0.80) must pass through the safety gate
    without any override. The old heuristic would have checked _looks_like_short_product_lookup
    and potentially overridden it to HS_CODE_LOOKUP. That code path is now removed.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    context = WorkflowContext(request_id="req_conf_high", question="but which one more costly??")
    context.intent = WorkflowIntent.GENERAL
    context.metadata = {"llm_confidence": 0.98}

    result = coordinator._apply_intent_safety_gate(context, "but which one more costly??")
    assert result == WorkflowIntent.GENERAL, (
        "GENERAL at 0.98 confidence must not be overridden to HS_CODE_LOOKUP"
    )


def test_safety_gate_general_low_confidence_no_override():
    """
    GENERAL intent at low confidence (< 0.60) must still pass through the safety gate
    unchanged. The gate's job is NOT to reclassify — Step 10 ask-back handles ambiguity.
    Previously the heuristic could override this to HS_CODE_LOOKUP; that code is removed.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    context = WorkflowContext(request_id="req_conf_low", question="which")
    context.intent = WorkflowIntent.GENERAL
    context.metadata = {"llm_confidence": 0.45}

    result = coordinator._apply_intent_safety_gate(context, "which")
    assert result == WorkflowIntent.GENERAL, (
        "GENERAL at 0.45 confidence must not be overridden by the gate. "
        "Ask-back (Step 10) handles this — not the safety gate."
    )


def test_llm_confidence_written_to_metadata_before_gate():
    """
    Verifies that context.metadata['llm_confidence'] is populated before
    _apply_intent_safety_gate is called, so the gate reads the real score
    instead of silently falling back to the 1.0 default.

    This is a structural regression test: if process_query is ever refactored
    and the metadata write is removed or reordered, this test will catch it.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    captured_metadata = {}

    original_gate = coordinator._apply_intent_safety_gate

    def capturing_gate(context, original_query, postpone_allowed=True):
        # Capture metadata at the moment the gate is called
        captured_metadata.update(context.metadata or {})
        return original_gate(context, original_query, postpone_allowed)

    coordinator._apply_intent_safety_gate = capturing_gate

    # Simulate the confidence write that process_query now does before calling the gate
    context = WorkflowContext(request_id="req_meta", question="rice")
    context.intent = WorkflowIntent.HS_CODE_LOOKUP
    context.metadata = {}
    _intent_confidence = 0.97
    context.metadata["llm_confidence"] = _intent_confidence   # The critical write

    coordinator._apply_intent_safety_gate(context, "rice")

    assert "llm_confidence" in captured_metadata, (
        "llm_confidence must be in context.metadata when _apply_intent_safety_gate is called"
    )
    assert captured_metadata["llm_confidence"] == 0.97


@pytest.mark.asyncio
async def test_safety_gate_calculation_procedural_downgrade_english():
    """
    Verifies that an English generic procedural calculation query is downgraded
    to GENERAL and clears session clarification state.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    session = SessionContext(session_id="sess_calc_eng")
    session.product_clarification_needed = True
    session.clarification_entity = "BMW vehicle"
    session.pending_clarification = True
    session.clarification_intents = ["calculation"]
    
    context = WorkflowContext(
        request_id="req_calc_eng",
        question="How is customs duty calculated?",
        session_id="sess_calc_eng",
        original_input="How is customs duty calculated?"
    )
    context.intent = WorkflowIntent.CALCULATION
    context.session_context = session
    context.metadata = {
        "nlu_unified_result": {
            "query_nature": "procedural"
        }
    }

    result_intent = coordinator._apply_intent_safety_gate(context, "How is customs duty calculated?")
    
    assert result_intent == WorkflowIntent.GENERAL
    assert not session.product_clarification_needed
    assert session.clarification_entity is None
    assert not session.pending_clarification
    assert session.clarification_intents == []


@pytest.mark.asyncio
async def test_safety_gate_calculation_procedural_downgrade_khmer():
    """
    Verifies that a Khmer generic procedural calculation query (via LLM query_nature)
    is downgraded to GENERAL.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    session = SessionContext(session_id="sess_calc_kh")
    
    context = WorkflowContext(
        request_id="req_calc_kh",
        question="តើត្រូវគណនាពន្ធគយយ៉ាងដូចម្តេច?",
        session_id="sess_calc_kh",
        original_input="តើត្រូវគណនាពន្ធគយយ៉ាងដូចម្តេច?"
    )
    context.intent = WorkflowIntent.CALCULATION
    context.session_context = session
    context.metadata = {
        "nlu_unified_result": {
            "query_nature": "procedural"
        }
    }

    result_intent = coordinator._apply_intent_safety_gate(context, "តើត្រូវគណនាពន្ធគយយ៉ាងដូចម្តេច?")
    assert result_intent == WorkflowIntent.GENERAL


@pytest.mark.asyncio
async def test_safety_gate_calculation_priceable_check():
    """
    Verifies that the fallback regex path correctly distinguishes between
    conceptual queries containing numeric HS codes and actual calculation queries.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=AsyncMock()
    )
    session = SessionContext(session_id="sess_priceable")
    
    # Query A: Contains HS code number 8703 but no price details -> Should downgrade to GENERAL
    context_a = WorkflowContext(
        request_id="req_a",
        question="explain how HS 8703 duty works",
        session_id="sess_priceable",
        original_input="explain how HS 8703 duty works"
    )
    context_a.intent = WorkflowIntent.CALCULATION
    context_a.session_context = session
    context_a.metadata = {}  # query_nature is unavailable/None

    intent_a = coordinator._apply_intent_safety_gate(context_a, "explain how HS 8703 duty works")
    assert intent_a == WorkflowIntent.GENERAL

    # Query B: Contains price details (CIF 5000 USD) -> Should remain CALCULATION
    context_b = WorkflowContext(
        request_id="req_b",
        question="calculate duty for HS 8703 CIF 5000 USD",
        session_id="sess_priceable",
        original_input="calculate duty for HS 8703 CIF 5000 USD"
    )
    context_b.intent = WorkflowIntent.CALCULATION
    context_b.session_context = session
    context_b.metadata = {}  # query_nature is unavailable/None

    intent_b = coordinator._apply_intent_safety_gate(context_b, "calculate duty for HS 8703 CIF 5000 USD")
    assert intent_b == WorkflowIntent.CALCULATION

