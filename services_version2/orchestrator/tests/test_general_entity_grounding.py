import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.coordinator import ServiceCoordinator
from app.services.session_context import SessionContext
from app.services.workflow import WorkflowContext, WorkflowIntent, WorkflowStatus

@pytest.mark.asyncio
async def test_entity_miss_triggers_fallback_when_high_confidence():
    # Setup coordinator with mocked downstream services
    mock_general_client = AsyncMock()
    mock_general_client.ask.return_value = {
        "status": "success",
        "documents": [
            {"content": "Import tax in Cambodia is calculated based on Customs Value.", "score": 0.9}
        ],
        "final_answer": "Import tax is calculated generally.",
    }
    
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    
    # Mock LLM router/provider for parametric definition generation
    mock_provider = MagicMock()
    mock_provider.is_available.return_value = True
    mock_provider.model_name = "gemini-flash"
    
    mock_response = MagicMock()
    mock_response.text = "Mocked parametric fallback answer for laptop"
    
    # Mock generate_content call
    mock_provider.client.models.generate_content = MagicMock(return_value=mock_response)
    mock_llm.router.providers = {"gemini": mock_provider}
    
    coordinator = ServiceCoordinator(
        general_client=mock_general_client,
        llm_service=mock_llm,
        use_input_rewriter=True,
    )
    
    # Setup context
    session = SessionContext(session_id="sess_1")
    context = WorkflowContext(
        request_id="req_1",
        question="what is its import tax",
        session_id="sess_1",
        original_input="what is its import tax"
    )
    context.session_context = session
    context.intent = WorkflowIntent.GENERAL
    context.metadata["nlu_entity"] = "laptop"
    context.metadata["nlu_entity_confidence"] = "high"
    
    # Process
    await coordinator._handle_default(context)
    
    # Assertions
    # 1. Check retrieval result is set
    result = context.get_result("retrieval")
    assert result is not None
    # 2. Check source indicates parametric fallback was triggered due to entity miss
    assert result.get("source") == "llm_parametric_knowledge"
    # 3. Check parametric answer was generated and populated
    assert result.get("final_answer") == "Mocked parametric fallback answer for laptop"
    # 4. Check client was called with correct parameters
    mock_general_client.ask.assert_called_once()
    assert mock_general_client.ask.call_args[1].get("entity") == "laptop"


@pytest.mark.asyncio
async def test_entity_match_uses_rag_response():
    # Setup coordinator
    mock_general_client = AsyncMock()
    mock_general_client.ask.return_value = {
        "status": "success",
        "documents": [
            {"content": "Laptops and computers are subject to 0% duty rate in Cambodia.", "score": 0.9}
        ],
        "final_answer": "According to Cambodia Customs, laptops have 0% duty rate.",
    }
    
    mock_llm = MagicMock()
    coordinator = ServiceCoordinator(
        general_client=mock_general_client,
        llm_service=mock_llm,
        use_input_rewriter=True,
    )
    
    session = SessionContext(session_id="sess_2")
    context = WorkflowContext(
        request_id="req_2",
        question="what is its import tax",
        session_id="sess_2",
        original_input="what is its import tax"
    )
    context.session_context = session
    context.intent = WorkflowIntent.GENERAL
    context.metadata["nlu_entity"] = "laptop"
    context.metadata["nlu_entity_confidence"] = "high"
    
    await coordinator._handle_default(context)
    
    result = context.get_result("retrieval")
    assert result is not None
    # Should NOT trigger parametric fallback
    assert result.get("source") != "llm_parametric_knowledge"
    assert result.get("final_answer") == "According to Cambodia Customs, laptops have 0% duty rate."


@pytest.mark.asyncio
async def test_low_confidence_entity_does_not_trigger_fallback_on_miss():
    mock_general_client = AsyncMock()
    mock_general_client.ask.return_value = {
        "status": "success",
        "documents": [
            {"content": "Import tax in Cambodia is calculated based on Customs Value.", "score": 0.9}
        ],
        "final_answer": "Import tax is calculated generally.",
    }
    
    mock_llm = MagicMock()
    coordinator = ServiceCoordinator(
        general_client=mock_general_client,
        llm_service=mock_llm,
        use_input_rewriter=True,
    )
    
    session = SessionContext(session_id="sess_3")
    context = WorkflowContext(
        request_id="req_3",
        question="what is its import tax",
        session_id="sess_3",
        original_input="what is its import tax"
    )
    context.session_context = session
    context.intent = WorkflowIntent.GENERAL
    context.metadata["nlu_entity"] = "laptop"
    context.metadata["nlu_entity_confidence"] = "low"
    
    await coordinator._handle_default(context)
    
    result = context.get_result("retrieval")
    assert result is not None
    # Should NOT trigger parametric fallback because entity confidence is low
    assert result.get("source") != "llm_parametric_knowledge"
    assert result.get("final_answer") == "Import tax is calculated generally."


def test_is_entity_changed():
    from app.utils.entity_utils import is_entity_changed
    
    # 1. Must not bridge car -> telephone via "automobile"/"mobile"
    assert is_entity_changed("automobile", "telephone") is True
    
    # 2. Must not match "pc" substring in "500 pcs"
    assert is_entity_changed("500 pcs", "laptop") is True
    
    # 3. Subset case: gaming laptop vs laptop (should match as same)
    assert is_entity_changed("gaming laptop", "laptop") is False
    
    # 4. Multi-word/model-number entity synonym case
    assert is_entity_changed("iPhone 16 Pro Max", "smartphone") is False
    
    # 5. Distinct categories with overlapping modifier words (car vs car battery)
    assert is_entity_changed("car", "car battery") is True
    
    # 6. Identical or empty cases
    assert is_entity_changed("laptop", "laptop") is False
    assert is_entity_changed(None, "laptop") is False
    assert is_entity_changed("laptop", None) is False
