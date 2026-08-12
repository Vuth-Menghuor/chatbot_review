import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.coordinator import ServiceCoordinator, WorkflowIntent
from app.services.workflow import WorkflowContext, WorkflowStatus
from app.services.session_context import SessionContext
from app.ai.shims.validator_service import ValidationResult

async def mock_route_retrieval(ctx):
    ctx.set_result("retrieval", {"answer": "some answer", "status": "completed"})
    ctx.status = WorkflowStatus.COMPLETED

async def mock_route_calculator(ctx):
    ctx.set_result("calculation", {"answer": "some answer", "status": "completed"})
    ctx.status = WorkflowStatus.COMPLETED

@pytest.mark.asyncio
async def test_dynamic_switching_no_pin():
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=MagicMock()
    )
    
    # Mock llm_service to avoid coroutine exceptions
    coordinator.llm_service.is_available = MagicMock(return_value=False)
    coordinator.llm_service.translate_to_khmer = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.llm_service.translate_to_english = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.query_translator.llm_service = coordinator.llm_service

    # Mock rewriter_service
    session = SessionContext(session_id="test_sess_switch")
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()
    coordinator.rewriter_service.rewrite_input = AsyncMock(
        return_value=("some product", {})
    )
    
    # Bypass safety gate
    coordinator._apply_intent_safety_gate = MagicMock(side_effect=lambda ctx, q, **kwargs: ctx.intent)
    coordinator._route_query = AsyncMock(side_effect=mock_route_retrieval)
    
    # Mock first layer NLU result
    unified_result = {
        "requested_language": None,
        "is_language_explicitly_requested": False,
        "intent": "hs_code_lookup",
        "confidence": 0.95
    }
    coordinator.first_layer_service = MagicMock()
    coordinator.first_layer_service.get_request_unified_result = MagicMock(side_effect=lambda: unified_result)
    coordinator.first_layer_service._normalize_key = MagicMock(side_effect=lambda x: x.strip().lower() if x else "")

    mock_validation_result = ValidationResult.in_scope(reason="llm_validated:hs_code_lookup")
    mock_validation_result.llm_confidence = 0.95

    with patch("app.services.coordinator.get_validator") as mock_get_validator:
        mock_validator = MagicMock()
        mock_validator.validate_input_full_async = AsyncMock(return_value=mock_validation_result)
        mock_get_validator.return_value = mock_validator
        
        # Turn 1: User asks in Khmer (no explicit pin)
        unified_result["query"] = "តើកូដ HS សម្រាប់ម៉ូតូកង់បួនគឺជាអ្វី"
        response1 = await coordinator.process_query(
            question="តើកូដ HS សម្រាប់ម៉ូតូកង់បួនគឺជាអ្វី",
            session_id="test_sess_switch"
        )
        assert response1["metadata"]["language"] == "km"
        assert session.target_language == "km"
        assert session.is_language_pinned is False

        # Turn 2: User asks an unrelated English query (no pin)
        unified_result["query"] = "what about motor rice mill 6-digit"
        response2 = await coordinator.process_query(
            question="what about motor rice mill 6-digit",
            session_id="test_sess_switch"
        )
        assert response2["metadata"]["language"] == "en"
        assert session.target_language == "en"
        assert session.is_language_pinned is False

@pytest.mark.asyncio
async def test_pin_persistence_across_three_turns():
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=MagicMock()
    )
    
    coordinator.llm_service.is_available = MagicMock(return_value=False)
    coordinator.llm_service.translate_to_khmer = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.llm_service.translate_to_english = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.query_translator.llm_service = coordinator.llm_service

    session = SessionContext(session_id="test_sess_pin")
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()
    coordinator.rewriter_service.rewrite_input = AsyncMock(
        return_value=("some product", {})
    )
    
    coordinator._apply_intent_safety_gate = MagicMock(side_effect=lambda ctx, q, **kwargs: ctx.intent)
    coordinator._route_query = AsyncMock(side_effect=mock_route_retrieval)

    unified_result = {
        "requested_language": None,
        "is_language_explicitly_requested": False,
        "intent": "hs_code_lookup",
        "confidence": 0.95
    }
    coordinator.first_layer_service = MagicMock()
    coordinator.first_layer_service.get_request_unified_result = MagicMock(side_effect=lambda: unified_result)
    coordinator.first_layer_service._normalize_key = MagicMock(side_effect=lambda x: x.strip().lower() if x else "")

    mock_validation_result = ValidationResult.in_scope(reason="llm_validated:hs_code_lookup")
    mock_validation_result.llm_confidence = 0.95

    with patch("app.services.coordinator.get_validator") as mock_get_validator:
        mock_validator = MagicMock()
        mock_validator.validate_input_full_async = AsyncMock(return_value=mock_validation_result)
        mock_get_validator.return_value = mock_validator

        # Turn 1: User explicitly pins to Khmer (e.g. "in Khmer")
        unified_result["query"] = "in khmer please"
        unified_result["requested_language"] = "km"
        unified_result["is_language_explicitly_requested"] = True

        response1 = await coordinator.process_query(
            question="in khmer please",
            session_id="test_sess_pin"
        )
        assert response1["metadata"]["language"] == "km"
        assert session.target_language == "km"
        assert session.is_language_pinned is True

        # Turn 2: Unmarked English query
        unified_result["query"] = "what about 2024?"
        unified_result["requested_language"] = None
        unified_result["is_language_explicitly_requested"] = False
        
        response2 = await coordinator.process_query(
            question="what about 2024?",
            session_id="test_sess_pin"
        )
        assert response2["metadata"]["language"] == "km"
        assert session.target_language == "km"
        assert session.is_language_pinned is True

        # Turn 3: Unmarked English query again
        unified_result["query"] = "calculate duty"
        response3 = await coordinator.process_query(
            question="calculate duty",
            session_id="test_sess_pin"
        )
        assert response3["metadata"]["language"] == "km"
        assert session.target_language == "km"
        assert session.is_language_pinned is True

@pytest.mark.asyncio
async def test_explicit_auto_request_unpins_language():
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=MagicMock()
    )

    coordinator.llm_service.is_available = MagicMock(return_value=False)
    coordinator.llm_service.translate_to_khmer = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.llm_service.translate_to_english = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.query_translator.llm_service = coordinator.llm_service

    session = SessionContext(session_id="test_sess_auto_unpin")
    session.target_language = "km"
    session.is_language_pinned = True
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()
    coordinator.rewriter_service.rewrite_input = AsyncMock(
        return_value=("some product", {})
    )

    coordinator._apply_intent_safety_gate = MagicMock(side_effect=lambda ctx, q, **kwargs: ctx.intent)
    coordinator._route_query = AsyncMock(side_effect=mock_route_retrieval)

    unified_result = {
        "requested_language": None,
        "is_language_explicitly_requested": False,
        "intent": "hs_code_lookup",
        "confidence": 0.95,
    }
    coordinator.first_layer_service = MagicMock()
    coordinator.first_layer_service.get_request_unified_result = MagicMock(side_effect=lambda: unified_result)
    coordinator.first_layer_service._normalize_key = MagicMock(side_effect=lambda x: x.strip().lower() if x else "")

    mock_validation_result = ValidationResult.in_scope(reason="llm_validated:hs_code_lookup")
    mock_validation_result.llm_confidence = 0.95

    with patch("app.services.coordinator.get_validator") as mock_get_validator:
        mock_validator = MagicMock()
        mock_validator.validate_input_full_async = AsyncMock(return_value=mock_validation_result)
        mock_get_validator.return_value = mock_validator

        response = await coordinator.process_query(
            question="switch to auto language please",
            session_id="test_sess_auto_unpin"
        )

        assert response["metadata"]["language"] == "en"
        assert session.target_language == "en"
        assert session.is_language_pinned is False

@pytest.mark.asyncio
async def test_clarification_retention_short_fragment():
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=MagicMock()
    )
    
    coordinator.llm_service.is_available = MagicMock(return_value=False)
    coordinator.llm_service.translate_to_khmer = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.llm_service.translate_to_english = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.query_translator.llm_service = coordinator.llm_service

    session = SessionContext(session_id="test_sess_clar")
    # Simulate a prior turn where language was km and clarification is pending
    session.target_language = "km"
    session.pending_clarification = True
    session.clarification_intents = ["hs_code_lookup"]
    
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()
    coordinator.rewriter_service.rewrite_input = AsyncMock(
        return_value=("some product", {})
    )
    
    coordinator._apply_intent_safety_gate = MagicMock(side_effect=lambda ctx, q, **kwargs: ctx.intent)
    coordinator._route_query = AsyncMock(side_effect=mock_route_retrieval)
    
    unified_result = {
        "query": "used",
        "requested_language": None,
        "is_language_explicitly_requested": False,
        "intent": "hs_code_lookup",
        "confidence": 0.95
    }
    coordinator.first_layer_service = MagicMock()
    coordinator.first_layer_service.get_request_unified_result = MagicMock(side_effect=lambda: unified_result)
    coordinator.first_layer_service._normalize_key = MagicMock(side_effect=lambda x: x.strip().lower() if x else "")

    mock_validation_result = ValidationResult.in_scope(reason="llm_validated:hs_code_lookup")
    mock_validation_result.llm_confidence = 0.95

    with patch("app.services.coordinator.get_validator") as mock_get_validator:
        mock_validator = MagicMock()
        mock_validator.validate_input_full_async = AsyncMock(return_value=mock_validation_result)
        mock_get_validator.return_value = mock_validator

        # User answers with a short English fragment "used" (is_km = False)
        # It does not trigger a topic switch, keeping pending_clarification = True.
        response = await coordinator.process_query(
            question="used",
            session_id="test_sess_clar"
        )
        assert response["metadata"]["language"] == "km"
        assert session.target_language == "km"
        assert session.is_language_pinned is False

@pytest.mark.asyncio
async def test_clarification_retention_not_firing_on_topic_switch():
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=MagicMock()
    )
    
    coordinator.llm_service.is_available = MagicMock(return_value=False)
    coordinator.llm_service.translate_to_khmer = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.llm_service.translate_to_english = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.query_translator.llm_service = coordinator.llm_service

    session = SessionContext(session_id="test_sess_switch_topic")
    session.target_language = "km"
    session.pending_clarification = True
    session.clarification_intents = ["hs_code_lookup"]
    
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()
    coordinator.rewriter_service.rewrite_input = AsyncMock(
        return_value=("rice", {})
    )
    
    coordinator._apply_intent_safety_gate = MagicMock(side_effect=lambda ctx, q, **kwargs: ctx.intent)
    coordinator._route_query = AsyncMock(side_effect=mock_route_calculator)
    
    # Topic switch candidate intent: calculation (not in clarification_intents which is hs_code_lookup)
    unified_result = {
        "query": "calculate duty for rice cif 5000",
        "requested_language": None,
        "is_language_explicitly_requested": False,
        "intent": "calculation",
        "confidence": 0.95
    }
    coordinator.first_layer_service = MagicMock()
    coordinator.first_layer_service.get_request_unified_result = MagicMock(side_effect=lambda: unified_result)
    coordinator.first_layer_service._normalize_key = MagicMock(side_effect=lambda x: x.strip().lower() if x else "")

    mock_validation_result = ValidationResult.in_scope(reason="llm_validated:calculation")
    mock_validation_result.llm_confidence = 0.95

    with patch("app.services.coordinator.get_validator") as mock_get_validator:
        mock_validator = MagicMock()
        mock_validator.validate_input_full_async = AsyncMock(return_value=mock_validation_result)
        mock_get_validator.return_value = mock_validator

        # User asks a completely new English query (topic switch)
        # This triggers exiting clarification in Step 4, clearing pending_clarification
        response = await coordinator.process_query(
            question="calculate duty for rice cif 5000",
            session_id="test_sess_switch_topic"
        )
        assert response["metadata"]["language"] == "en"
        assert session.target_language == "en"
        assert session.pending_clarification is False

@pytest.mark.asyncio
async def test_pure_language_request_direct_translation():
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        llm_service=MagicMock()
    )
    
    coordinator.llm_service.is_available = MagicMock(return_value=False)
    coordinator.llm_service.translate_to_khmer = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.llm_service.translate_to_english = AsyncMock(side_effect=lambda text: f"<translation>{text}</translation>")
    coordinator.query_translator.llm_service = coordinator.llm_service

    session = SessionContext(session_id="test_sess_direct_trans")
    session.add_turn(user="what is the hs code for car", bot="The HS code for a car is 8703.")
    session.last_intent = "hs_code_lookup"
    
    coordinator.rewriter_service.get_or_create_session = MagicMock(return_value=session)
    coordinator.rewriter_service.update_session_context = MagicMock()
    coordinator.rewriter_service.rewrite_input = AsyncMock(
        return_value=("car", {})
    )
    
    # We mock _route_query to ensure it is never called on Turn 2
    mock_route = AsyncMock(side_effect=mock_route_retrieval)
    coordinator._route_query = mock_route

    with patch("app.services.translator.QueryTranslator.translate_to_khmer", side_effect=lambda text: f"<translation>{text}</translation>") as mock_trans_km, \
         patch("app.services.translator.QueryTranslator.translate_to_english", side_effect=lambda text: f"<translation>{text}</translation>") as mock_trans_en:
         
        # Process Turn 2: Pure language modifier
        response = await coordinator.process_query(
            question="in Khmer please",
            session_id="test_sess_direct_trans"
        )
        
        # Assert that _route_query was never called on Turn 2
        mock_route.assert_not_called()
        
        # Assert response translated the last turn's answer directly
        assert response["answer"] == "<translation>The HS code for a car is 8703.</translation>"
        assert response["metadata"]["language"] == "km"
        assert session.target_language == "km"
        assert session.is_language_pinned is True
