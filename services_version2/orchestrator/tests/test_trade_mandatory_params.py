import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.coordinator import ServiceCoordinator, WorkflowIntent
from app.services.workflow import WorkflowContext, WorkflowStatus
from app.services.session_context import SessionContext

@pytest.mark.asyncio
async def test_trade_query_missing_mandatory_params_and_metadata():
    """Verify that _handle_trade_query triggers clarification with structured metadata when parameters are missing."""
    coordinator = ServiceCoordinator(
        trade_data_client=AsyncMock(),
        use_input_rewriter=False,
    )
    
    session = SessionContext(session_id="sess_1")
    context = WorkflowContext(request_id="req1", question="can you tell me the trade data", session_id="sess_1")
    context.session_context = session
    context.intent = WorkflowIntent.TRADE_QUERY

    await coordinator._handle_trade_query(context)
    
    assert context.status == WorkflowStatus.CLARIFICATION_REQUIRED
    res = context.trade_query_result
    assert res.get("clarification_required") is True
    
    metadata = res.get("metadata", {})
    assert metadata.get("pending_clarification") is True
    assert isinstance(metadata.get("clarification_entity"), list)
    assert "product" in metadata["clarification_entity"]
    assert "trade_period" in metadata["clarification_entity"]
    assert "clarification_expected_terms" in metadata
    assert session.ask_back_count == 1

@pytest.mark.asyncio
async def test_trade_query_negation_and_escape_hatch():
    """Verify negation handling and escape hatch disclosure behavior."""
    coordinator = ServiceCoordinator(
        trade_data_client=AsyncMock(),
        use_input_rewriter=False,
    )
    coordinator.trade_data_client.query = AsyncMock(return_value={"status": "success", "answer": "Data table for import 2024"})

    # Escape hatch query ("whatever")
    session = SessionContext(session_id="sess_2")
    context = WorkflowContext(request_id="req2", question="show me whatever trade data for coffee", session_id="sess_2")
    context.session_context = session
    context.intent = WorkflowIntent.TRADE_QUERY

    await coordinator._handle_trade_query(context)

    assert context.status == WorkflowStatus.COMPLETED
    res = context.trade_query_result
    assert "_Showing trade statistics using assumed defaults:" in res.get("answer", "")
    assert session.ask_back_count == 0

def test_is_slot_fragment_reply():
    """Verify deterministic Layer 1 structural gate (_is_slot_fragment_reply)."""
    coordinator = ServiceCoordinator(trade_data_client=AsyncMock(), use_input_rewriter=False)
    clarification_intents = ["trade_query"]

    # Parameter replies -> Must return True
    assert coordinator._is_slot_fragment_reply("partner country: USA, flow: import", clarification_intents) is True
    assert coordinator._is_slot_fragment_reply("q1 2026", clarification_intents) is True
    assert coordinator._is_slot_fragment_reply("USA", clarification_intents) is True
    assert coordinator._is_slot_fragment_reply("import", clarification_intents) is True

    # Conversational topic switches / Questions -> Must return False
    assert coordinator._is_slot_fragment_reply("actually never mind, what documents do I need for informal import", clarification_intents) is False
    assert coordinator._is_slot_fragment_reply("what changed in customs policy since 2020", clarification_intents) is False
    assert coordinator._is_slot_fragment_reply("where can I apply for an import license", clarification_intents) is False

@pytest.mark.asyncio
async def test_definition_query_llm_fallback():
    """Verify that when RAG returns no definition, LLM parametric fallback generates the answer."""
    coordinator = ServiceCoordinator(
        general_client=AsyncMock(),
        use_input_rewriter=False,
    )
    coordinator.general_client.ask.return_value = {
        "status": "success",
        "answer": "Based on the provided documents, there is no definition of 'CKD' available.",
        "is_generic": True
    }
    
    coordinator.llm_service = MagicMock()
    coordinator.llm_service.is_available.return_value = True
    provider = MagicMock()
    provider.is_available.return_value = True
    mock_resp = MagicMock()
    mock_resp.text = "CKD stands for Completely Knocked Down. It refers to imported unassembled parts."
    provider.client.models.generate_content.return_value = mock_resp
    coordinator.llm_service.router.providers = {"gemini": provider}

    context = WorkflowContext(request_id="req3", question="what is CKD?")
    context.intent = WorkflowIntent.GENERAL

    await coordinator._handle_default(context)

    assert context.status == WorkflowStatus.COMPLETED
    res = context.get_result("retrieval")
    assert "Completely Knocked Down" in res.get("answer", "")
    assert res.get("source") == "llm_parametric_knowledge"

@pytest.mark.asyncio
async def test_today_date_query_llm_fallback():
    """Verify that when RAG returns 'do not contain information regarding today's date', LLM fallback answers."""
    coordinator = ServiceCoordinator(
        general_client=AsyncMock(),
        use_input_rewriter=False,
    )
    coordinator.general_client.ask.return_value = {
        "status": "success",
        "answer": "The provided documents do not contain information regarding today's date.",
        "is_generic": True
    }
    
    coordinator.llm_service = MagicMock()
    coordinator.llm_service.is_available.return_value = True
    provider = MagicMock()
    provider.is_available.return_value = True
    mock_resp = MagicMock()
    mock_resp.text = "Today is Friday, July 24, 2026."
    provider.client.models.generate_content.return_value = mock_resp
    coordinator.llm_service.router.providers = {"gemini": provider}

    context = WorkflowContext(request_id="req4", question="can you tell me what today date is?")
    context.intent = WorkflowIntent.GENERAL

    await coordinator._handle_default(context)

    assert context.status == WorkflowStatus.COMPLETED
    res = context.get_result("retrieval")
    assert "July 24, 2026" in res.get("answer", "")
    assert res.get("source") == "llm_parametric_knowledge"
