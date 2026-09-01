import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure app is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.coordinator import ServiceCoordinator
from app.services.session_context import SessionContext
from app.services.workflow import WorkflowContext, WorkflowIntent, WorkflowStatus

async def test_parity():
    print("Initializing parity checks...")
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        use_input_rewriter=True,
    )
    
    # 1. Test build update payload (three-state entity tracking)
    session = SessionContext(session_id="sess_parity")
    session.last_entity = "car"
    
    payload = coordinator._build_session_update_payload(
        raw_query="actually none",
        normalized_query="actually none",
        intent_value="general",
        session_context=session,
        nlu_entity=None,
        has_nlu_entity=True,
        nlu_entity_confidence="explicit_none"
    )
    # State 2 clearing correction fragment -> should be None
    assert payload["last_entity"] is None, f"Expected None, got {payload['last_entity']}"
    
    # 2. Test merge pending with clarification
    session.last_entity = "sedan car"
    session.set_pending_clarification(["calculation"], "cif 2000")
    was_awaiting = session.is_awaiting_clarification()
    pending_query = session.resolve_clarification("calculation")
    
    merged = coordinator._merge_pending_with_clarification(
        pending_query=pending_query,
        clarification_response="cif 2000",
        resolved_intent="calculation",
        session_last_entity="sedan car",
        session_context=session,
        was_clarification_pending=was_awaiting
    )
    assert "sedan car" in merged.lower(), f"Expected sedan car to be merged, got '{merged}'"
    
    print("✅ All local coordinator parity tests passed successfully!")
 
if __name__ == "__main__":
    asyncio.run(test_parity())
