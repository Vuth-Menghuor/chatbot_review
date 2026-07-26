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
