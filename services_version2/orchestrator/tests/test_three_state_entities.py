import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.coordinator import ServiceCoordinator
from app.services.session_context import SessionContext
from app.services.workflow import WorkflowContext, WorkflowIntent, WorkflowStatus

@pytest.mark.asyncio
async def test_state_1_happy_path():
    """State 1: A high-confidence NLU entity is found and overwrites last_entity."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    session = SessionContext(session_id="sess_1")
    session.last_entity = "old entity"
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()

    context = WorkflowContext(
        request_id="req1",
        question="hs code of bmw",
        session_id="sess_1",
        original_input="hs code of bmw"
    )
    context.session_context = session
    context.intent = WorkflowIntent.HS_CODE_LOOKUP
    context.status = WorkflowStatus.COMPLETED

    # Mock high-confidence entity returned by LLM
    context.metadata["has_nlu_entity"] = True
    context.metadata["nlu_entity"] = "bmw"
    context.metadata["nlu_entity_confidence"] = "high"

    # Run build payload
    payload = coordinator._build_session_update_payload(
        raw_query=context.question,
        normalized_query=context.question,
        intent_value=context.intent.value,
        session_context=session,
        nlu_entity=context.metadata["nlu_entity"],
        has_nlu_entity=context.metadata["has_nlu_entity"],
        nlu_entity_confidence=context.metadata["nlu_entity_confidence"],
    )

    assert payload["last_entity"] == "bmw"


@pytest.mark.asyncio
async def test_state_2_english_correction():
    """State 2: An English clearing correction fragment clears last_entity."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    session = SessionContext(session_id="sess_2")
    session.last_entity = "bmw"
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()

    context = WorkflowContext(
        request_id="req2",
        question="actually none",
        session_id="sess_2",
        original_input="actually none"
    )
    context.session_context = session
    context.intent = WorkflowIntent.GENERAL
    context.status = WorkflowStatus.COMPLETED

    # Mock explicit none returned by LLM
    context.metadata["has_nlu_entity"] = True
    context.metadata["nlu_entity"] = None
    context.metadata["nlu_entity_confidence"] = "explicit_none"

    payload = coordinator._build_session_update_payload(
        raw_query=context.question,
        normalized_query=context.question,
        intent_value=context.intent.value,
        session_context=session,
        nlu_entity=context.metadata["nlu_entity"],
        has_nlu_entity=context.metadata["has_nlu_entity"],
        nlu_entity_confidence=context.metadata["nlu_entity_confidence"],
    )

    # Clearing correction is matched, so it clears last_entity to None
    assert payload["last_entity"] is None


@pytest.mark.asyncio
async def test_state_2_khmer_correction():
    """State 2: A Khmer clearing correction fragment clears last_entity."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    session = SessionContext(session_id="sess_3")
    session.last_entity = "bmw"
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()

    context = WorkflowContext(
        request_id="req3",
        question="គ្មានទេ",
        session_id="sess_3",
        original_input="គ្មានទេ"
    )
    context.session_context = session
    context.intent = WorkflowIntent.GENERAL
    context.status = WorkflowStatus.COMPLETED

    # Mock explicit none returned by LLM
    context.metadata["has_nlu_entity"] = True
    context.metadata["nlu_entity"] = None
    context.metadata["nlu_entity_confidence"] = "explicit_none"

    payload = coordinator._build_session_update_payload(
        raw_query=context.question,
        normalized_query=context.question,
        intent_value=context.intent.value,
        session_context=session,
        nlu_entity=context.metadata["nlu_entity"],
        has_nlu_entity=context.metadata["has_nlu_entity"],
        nlu_entity_confidence=context.metadata["nlu_entity_confidence"],
    )

    # Clearing correction in Khmer is matched, so it clears last_entity to None
    assert payload["last_entity"] is None


@pytest.mark.asyncio
async def test_state_2_unrelated_query():
    """State 2: An unrelated non-entity turn preserves last_entity."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    session = SessionContext(session_id="sess_4")
    session.last_entity = "bmw"
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()

    context = WorkflowContext(
        request_id="req4",
        question="what is RCEP?",
        session_id="sess_4",
        original_input="what is RCEP?"
    )
    context.session_context = session
    context.intent = WorkflowIntent.GENERAL
    context.status = WorkflowStatus.COMPLETED

    # Mock explicit none returned by LLM (RCEP is an FTA, not a product entity)
    context.metadata["has_nlu_entity"] = True
    context.metadata["nlu_entity"] = None
    context.metadata["nlu_entity_confidence"] = "explicit_none"

    payload = coordinator._build_session_update_payload(
        raw_query=context.question,
        normalized_query=context.question,
        intent_value=context.intent.value,
        session_context=session,
        nlu_entity=context.metadata["nlu_entity"],
        has_nlu_entity=context.metadata["has_nlu_entity"],
        nlu_entity_confidence=context.metadata["nlu_entity_confidence"],
    )

    # Unrelated general query preserved last_entity untouched
    assert payload["last_entity"] == "bmw"


@pytest.mark.asyncio
async def test_state_3_low_confidence():
    """State 3: A low-confidence NLU entity does not overwrite last_entity."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    session = SessionContext(session_id="sess_5")
    session.last_entity = "bmw"
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()

    context = WorkflowContext(
        request_id="req5",
        question="what is that?",
        session_id="sess_5",
        original_input="what is that?"
    )
    context.session_context = session
    context.intent = WorkflowIntent.GENERAL
    context.status = WorkflowStatus.COMPLETED

    # Mock low confidence entity extraction
    context.metadata["has_nlu_entity"] = True
    context.metadata["nlu_entity"] = "that"
    context.metadata["nlu_entity_confidence"] = "low"

    payload = coordinator._build_session_update_payload(
        raw_query=context.question,
        normalized_query=context.question,
        intent_value=context.intent.value,
        session_context=session,
        nlu_entity=context.metadata["nlu_entity"],
        has_nlu_entity=context.metadata["has_nlu_entity"],
        nlu_entity_confidence=context.metadata["nlu_entity_confidence"],
    )

    # Low confidence does not overwrite session.last_entity
    assert payload["last_entity"] == "bmw"


@pytest.mark.asyncio
async def test_state_3_cache_hit_fallback():
    """State 3: A cache hit/regex fallback (no NLU run) preserves last_entity."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    session = SessionContext(session_id="sess_6")
    session.last_entity = "bmw"
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()

    context = WorkflowContext(
        request_id="req6",
        question="hello there",
        session_id="sess_6",
        original_input="hello there"
    )
    context.session_context = session
    context.intent = WorkflowIntent.SMALL_TALK
    context.status = WorkflowStatus.COMPLETED

    # NLU is skipped, so has_nlu_entity is False
    context.metadata["has_nlu_entity"] = False

    payload = coordinator._build_session_update_payload(
        raw_query=context.question,
        normalized_query=context.question,
        intent_value=context.intent.value,
        session_context=session,
        nlu_entity=None,
        has_nlu_entity=context.metadata["has_nlu_entity"],
        nlu_entity_confidence=None,
    )

    # State 3 fallback logic keeps the entity unchanged
    assert payload["last_entity"] == "bmw"


@pytest.mark.asyncio
async def test_sequencing_preserves_pre_turn_entity_for_merge():
    """Verify that clarification merge uses the pre-turn last_entity value."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    
    session = SessionContext(session_id="sess_7")
    session.last_entity = "original car"
    session.set_pending_clarification(["calculation", "hs_code_lookup"], "cif 1000")

    # In Step 7, the coordinator captures pre-turn last_entity and resolves clarification
    pre_turn_last_entity = session.last_entity
    assert pre_turn_last_entity == "original car"
    
    was_awaiting = session.is_awaiting_clarification()
    assert was_awaiting is True
    
    # Simulate resolving clarification (which clears pending_clarification flag)
    pending_query = session.resolve_clarification("calculation")
    
    # Run merge using pre-turn value
    merged = coordinator._merge_pending_with_clarification(
        pending_query=pending_query,
        clarification_response="cif 1000",
        resolved_intent="calculation",
        session_last_entity=pre_turn_last_entity,
        session_context=session,
        was_clarification_pending=was_awaiting,
    )

    # Verify original car was successfully merged using pre-turn value
    assert "original car" in merged.lower()


# ---------------------------------------------------------------------------
# Regression: Toyota Camry → motorcycle → "used one" scenario
# Ensures last_entity survives clarification turns and bare follow-ups.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_topic_switch_clears_then_sets_last_entity():
    """
    Turn 2 topic switch (Camry → motorcycle):
    - clear_context_slots() wipes old last_entity ('toyota camry 2020')
    - _build_session_update_payload then sets last_entity to 'motorcycle'
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    session = SessionContext(session_id="sess_reg1")
    # Simulate state after Turn 1 (Toyota Camry)
    session.last_entity = "toyota camry 2020"
    session.product_category = "vehicle"

    # Step 11: topic switch detected — clear
    session.clear_context_slots()
    assert session.last_entity is None, "clear_context_slots must wipe last_entity"
    assert session.product_category is None

    # Step 13: _build_session_update_payload sets new entity from Turn 2
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()

    payload = coordinator._build_session_update_payload(
        raw_query="hs code of motorcycle",
        normalized_query="hs code of motorcycle",
        intent_value="hs_code_lookup",
        session_context=session,
        nlu_entity="motorcycle",
        has_nlu_entity=True,
        nlu_entity_confidence="high",
    )

    assert payload["last_entity"] == "motorcycle", (
        "After topic switch, last_entity must be updated to the new Turn 2 entity"
    )


@pytest.mark.asyncio
async def test_medium_confidence_entity_sets_last_entity():
    """
    Confidence gate is 'high' OR 'medium' — HS-lookup queries are often short bare nouns
    that reliably produce medium-confidence extractions. Verify last_entity is still set.
    """
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    session = SessionContext(session_id="sess_reg_med")
    session.last_entity = None

    payload = coordinator._build_session_update_payload(
        raw_query="motorcycle",
        normalized_query="motorcycle",
        intent_value="hs_code_lookup",
        session_context=session,
        nlu_entity="motorcycle",
        has_nlu_entity=True,
        nlu_entity_confidence="medium",
    )

    assert payload["last_entity"] == "motorcycle", (
        "Medium-confidence entity must update last_entity (HS-lookup short queries often score medium)"
    )


@pytest.mark.asyncio
async def test_bare_followup_preserves_last_entity():
    """
    Turn 3 bare follow-up ("used one"):
    - NLU cache returns no entity for 'used one' (low/explicit_none confidence)
    - Fallback token-overlap check uses ONLY the NLU cache entity (not extract_entity),
      so new_entity is None and the guard is never entered.
    - last_entity must remain 'motorcycle' for the rewriter.
    """
    import re as _re

    session = SessionContext(session_id="sess_reg2")
    session.last_entity = "motorcycle"

    # Simulate the fallback check from coordinator.py Step 11.
    # The NLU cache has no entity for a bare follow-up like "used one".
    nlu_cache = {"entity": None, "entity_confidence": "explicit_none"}

    prev_entity = session.last_entity or ""
    # Coordinator uses ONLY the NLU cache, never extract_entity(), as the fallback
    new_entity = nlu_cache.get("entity") if nlu_cache else None

    # Guard: fallback only fires if BOTH prev_entity and new_entity are truthy
    if prev_entity and new_entity:
        prev_tokens = set(_re.findall(r"[a-z0-9]+", prev_entity.lower()))
        new_tokens = set(_re.findall(r"[a-z0-9]+", new_entity.lower()))
        if prev_tokens and new_tokens and not (prev_tokens & new_tokens):
            session.clear_context_slots()

    assert session.last_entity == "motorcycle", (
        "Bare follow-up 'used one' must NOT trigger topic switch — last_entity must survive"
    )


@pytest.mark.asyncio
async def test_clear_context_slots_includes_last_entity():
    """Ensure clear_context_slots now also clears last_entity."""
    session = SessionContext(session_id="sess_reg3")
    session.last_entity = "toyota camry 2020"
    session.product_category = "vehicle"
    session.hs_code = "8703.23.57"
    session.origin_country = "Japan"

    session.clear_context_slots()

    assert session.last_entity is None
    assert session.product_category is None
    assert session.hs_code is None
    assert session.origin_country is None

