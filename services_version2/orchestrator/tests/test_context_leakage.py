import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.coordinator import ServiceCoordinator
from app.services.session_context import SessionContext
from app.services.workflow import WorkflowContext, WorkflowIntent, WorkflowStatus

@pytest.mark.asyncio
async def test_is_rewrite_valid_swapped_entity_rejected():
    """Verify that _is_rewrite_valid rejects a rewritten query that replaces a new entity with a stale one."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    
    session = SessionContext(session_id="sess_leak_1")
    session.last_entity = "car"
    
    context = WorkflowContext(
        request_id="req_leak_1",
        question="need tax calc for bus, cif $40,000, importing from china",
        session_id="sess_leak_1",
        original_input="need tax calc for bus, cif $40,000, importing from china"
    )
    context.session_context = session
    context.metadata["has_nlu_entity"] = True
    context.metadata["nlu_entity"] = "bus"
    context.metadata["nlu_entity_confidence"] = "high"

    original_query = "need tax calc for bus, cif $40,000, importing from china"
    rewritten_query = "calculate import tax car CIF 40000 USD China"

    is_valid = coordinator._is_rewrite_valid(
        original_query=original_query,
        rewritten_query=rewritten_query,
        intent=WorkflowIntent.CALCULATION,
        context=context
    )
    assert is_valid is False


@pytest.mark.asyncio
async def test_is_rewrite_valid_correct_entity_accepted():
    """Verify that _is_rewrite_valid accepts a rewritten query that retains the correct new entity."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    
    session = SessionContext(session_id="sess_leak_2")
    session.last_entity = "car"
    
    context = WorkflowContext(
        request_id="req_leak_2",
        question="need tax calc for bus, cif $40,000, importing from china",
        session_id="sess_leak_2",
        original_input="need tax calc for bus, cif $40,000, importing from china"
    )
    context.session_context = session
    context.metadata["has_nlu_entity"] = True
    context.metadata["nlu_entity"] = "bus"
    context.metadata["nlu_entity_confidence"] = "high"

    original_query = "need tax calc for bus, cif $40,000, importing from china"
    rewritten_query = "calculate import tax bus CIF 40000 USD China"

    is_valid = coordinator._is_rewrite_valid(
        original_query=original_query,
        rewritten_query=rewritten_query,
        intent=WorkflowIntent.CALCULATION,
        context=context
    )
    assert is_valid is True


@pytest.mark.asyncio
async def test_is_rewrite_valid_no_swap_fallback_accepted():
    """Verify that if no swap happens (e.g., fallback to original query), the rewrite is considered valid."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    
    session = SessionContext(session_id="sess_leak_3")
    session.last_entity = "car"
    
    context = WorkflowContext(
        request_id="req_leak_3",
        question="need tax calc for bus, cif $40,000, importing from china",
        session_id="sess_leak_3",
        original_input="need tax calc for bus, cif $40,000, importing from china"
    )
    context.session_context = session
    context.metadata["has_nlu_entity"] = True
    context.metadata["nlu_entity"] = "bus"
    context.metadata["nlu_entity_confidence"] = "high"

    original_query = "need tax calc for bus, cif $40,000, importing from china"
    rewritten_query = original_query

    is_valid = coordinator._is_rewrite_valid(
        original_query=original_query,
        rewritten_query=rewritten_query,
        intent=WorkflowIntent.CALCULATION,
        context=context
    )
    assert is_valid is True


@pytest.mark.asyncio
async def test_is_rewrite_valid_no_context_accepted():
    """Verify that if no session context is present, the rewrite is accepted by default."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )

    original_query = "need tax calc for bus, cif $40,000, importing from china"
    rewritten_query = "calculate import tax car CIF 40000 USD China"

    is_valid = coordinator._is_rewrite_valid(
        original_query=original_query,
        rewritten_query=rewritten_query,
        intent=WorkflowIntent.CALCULATION,
        context=None
    )
    assert is_valid is True
