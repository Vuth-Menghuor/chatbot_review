import sys
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.coordinator import ServiceCoordinator, WorkflowIntent
from app.services.handlers.calculation import CalculationHandler
from app.services.session_context import SessionContext
from app.services.workflow import WorkflowContext, WorkflowStatus
from app.core.config import LLMFirstLayerConfig
from app.ai.analyzer import get_llm_first_layer_service, unified_result_var
from app.ai.shims.validator_service import get_validator, ValidationResult

def set_nlu_cache(query: str, intent: str, confidence: float = 0.95):
    unified_result_var.set({
        "query": query,
        "intent": intent,
        "confidence": confidence,
        "is_safe": True,
        "is_on_topic": True
    })

def make_mock_calculator(answer="Duty is $200"):
    calc = AsyncMock()
    calc.query.return_value = {"status": "success", "answer": answer, "final_answer": answer, "result": "Calculation result"}
    calc.calculate_duty.return_value = {"status": "success", "answer": answer, "final_answer": answer, "citations": []}
    return calc

@pytest.mark.asyncio
async def test_capability_hs_code_lookup_merge():
    """Verify that a generic HS code capability check triggers ask-back and merges user response on turn 2."""
    mock_retrieval = AsyncMock()
    mock_retrieval.ask.return_value = {"status": "success", "final_answer": "Standard retrieval answer", "citations": []}
    mock_retrieval.hs_code_lookup.return_value = {"status": "success", "final_answer": "HS lookup result for potatoes", "citations": []}
    mock_retrieval.general = mock_retrieval.ask
    
    mock_calculator = make_mock_calculator()
    mock_trade = MagicMock()
    
    config = LLMFirstLayerConfig()
    first_layer = get_llm_first_layer_service(config)
    
    mock_llm = MagicMock()
    first_layer._get_llm_service = MagicMock(return_value=mock_llm)
    
    coordinator = ServiceCoordinator(
        retrieval_client=mock_retrieval,
        general_client=mock_retrieval,
        calculator_client=mock_calculator,
        trade_data_client=mock_trade,
        first_layer_service=first_layer,
        use_input_rewriter=True
    )
    coordinator.llm_service = mock_llm
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    # Mock NLU classification
    def mock_detect(q):
        if "can you help me with hs code" in q:
            return WorkflowIntent.HS_CODE_LOOKUP, 0.55
        if "potatoes" in q:
            return WorkflowIntent.HS_CODE_LOOKUP, 0.95
        return WorkflowIntent.GENERAL, 0.90
    coordinator.workflow_executor.detect_intent_with_confidence = mock_detect
    
    coordinator.rewriter_service.rewrite_input = AsyncMock(side_effect=lambda user_input, **kwargs: (user_input, {}))
    
    session_id = "test_sess_hs_cap"
    session = first_layer.session_manager.get_or_create_session(session_id)
    session.pending_clarification = False
    session.clarification_intents = []
    session.product_clarification_needed = False
    session.turns = []
    
    # Turn 1: Capability request
    res = await coordinator.process_query(question="can you help me with hs code", session_id=session_id)
    assert res.get("status") == "clarification_required"
    assert any(kw in res.get("answer", "").lower() for kw in ["product", "look up", "hs code", "description", "item"])
    assert session.pending_clarification is True
    assert "hs_code_lookup" in session.clarification_intents
    
    # Turn 2: User provides missing product spec (set NLU cache to simulate prewarm)
    set_nlu_cache("potatoes", "hs_code_lookup", 0.95)
    res2 = await coordinator.process_query(question="potatoes", session_id=session_id)
    assert res2.get("intent") == "hs_code_lookup"
    assert res2.get("status") == "completed"
    assert "HS lookup result for potatoes" in res2.get("answer", "")
    assert session.pending_clarification is False


@pytest.mark.asyncio
async def test_capability_calculation_merge():
    """Verify that a generic calculation capability check triggers ask-back and merges user response on turn 2."""
    mock_retrieval = AsyncMock()
    mock_calculator = make_mock_calculator()
    mock_calculator.query.return_value = {"status": "success", "result": "Calculation result for $2000 laptop from China"}
    mock_calculator.calculate_duty.return_value = {"status": "success", "final_answer": "Duty is $500", "citations": []}
    mock_trade = MagicMock()
    
    config = LLMFirstLayerConfig()
    first_layer = get_llm_first_layer_service(config)
    
    mock_llm = MagicMock()
    first_layer._get_llm_service = MagicMock(return_value=mock_llm)
    
    coordinator = ServiceCoordinator(
        retrieval_client=mock_retrieval,
        general_client=mock_retrieval,
        calculator_client=mock_calculator,
        trade_data_client=mock_trade,
        first_layer_service=first_layer,
        use_input_rewriter=True
    )
    coordinator.llm_service = mock_llm
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    def mock_detect(q):
        if "help me calculate duty" in q:
            return WorkflowIntent.CALCULATION, 0.55
        if "2000" in q:
            return WorkflowIntent.CALCULATION, 0.95
        return WorkflowIntent.GENERAL, 0.90
    coordinator.workflow_executor.detect_intent_with_confidence = mock_detect
    
    coordinator.rewriter_service.rewrite_input = AsyncMock(side_effect=lambda user_input, **kwargs: (user_input, {}))
    
    session_id = "test_sess_calc_cap"
    session = first_layer.session_manager.get_or_create_session(session_id)
    session.pending_clarification = False
    session.clarification_intents = []
    session.product_clarification_needed = False
    session.turns = []
    
    # Turn 1: Capability request
    res = await coordinator.process_query(question="help me calculate duty", session_id=session_id)
    assert res.get("status") == "clarification_required"
    assert any(kw in res.get("answer", "").lower() for kw in ["product", "cif", "import", "duties", "taxes", "value", "details", "tax"])
    assert session.pending_clarification is True
    assert "calculation" in session.clarification_intents
    
    # Turn 2: User provides missing import details (set NLU cache to simulate prewarm)
    set_nlu_cache("$2000 laptop from China", "calculation", 0.95)
    res2 = await coordinator.process_query(question="$2000 laptop from China", session_id=session_id)
    assert res2.get("intent") == "calculation"
    assert res2.get("status") == "completed"
    assert session.pending_clarification is False


@pytest.mark.asyncio
async def test_calculation_blocks_fabricated_hs_code_during_open_product_clarification():
    """Verify that calculation cannot invent a fresh HS code while HS lookup clarification is still open."""
    mock_calculator = make_mock_calculator()
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=mock_calculator,
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator._execute_service_call = AsyncMock()

    session = SessionContext(session_id="sess_calc_hs_guard")
    session.product_clarification_needed = True
    session.clarification_entity = "motorcycle"
    session.clarification_candidate_codes = ["8703.23.00", "8703.24.00"]
    session.turns = [{"user": "what is the HS code for motorcycle?", "bot": "Please choose one of the candidates."}]

    context = WorkflowContext(
        request_id="req_calc_hs_guard",
        question="calculate duty for it",
        session_id="sess_calc_hs_guard",
        original_input="calculate duty for it",
    )
    context.intent = WorkflowIntent.CALCULATION
    context.session_context = session
    context.metadata = {}

    await CalculationHandler.handle(coordinator, context)

    assert context.status == WorkflowStatus.CLARIFICATION_REQUIRED
    assert mock_calculator.query.await_count == 0
    assert session.product_clarification_needed is True
    assert session.clarification_candidate_codes == ["8703.23.00", "8703.24.00"]
    assert context.calculation_result["clarification_required"] is True
    assert "HS code" in context.calculation_result["answer"]


@pytest.mark.asyncio
async def test_capability_trade_query_merge():
    """Verify that a generic trade data capability check triggers ask-back and merges user response on turn 2."""
    mock_retrieval = AsyncMock()
    mock_calculator = make_mock_calculator()
    mock_trade = AsyncMock()
    mock_trade.query.return_value = {"status": "success", "result": "Trade data result for rice"}
    mock_trade.get_trade_statistics.return_value = {"status": "success", "final_answer": "Trade stats for rice", "citations": []}
    
    config = LLMFirstLayerConfig()
    first_layer = get_llm_first_layer_service(config)
    
    mock_llm = MagicMock()
    first_layer._get_llm_service = MagicMock(return_value=mock_llm)
    
    coordinator = ServiceCoordinator(
        retrieval_client=mock_retrieval,
        general_client=mock_retrieval,
        calculator_client=mock_calculator,
        trade_data_client=mock_trade,
        first_layer_service=first_layer,
        use_input_rewriter=True
    )
    coordinator.llm_service = mock_llm
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    def mock_detect(q):
        if "can you help me with trade data" in q:
            return WorkflowIntent.TRADE_QUERY, 0.55
        if "rice" in q:
            return WorkflowIntent.TRADE_QUERY, 0.95
        return WorkflowIntent.GENERAL, 0.90
    coordinator.workflow_executor.detect_intent_with_confidence = mock_detect
    
    coordinator.rewriter_service.rewrite_input = AsyncMock(side_effect=lambda user_input, **kwargs: (user_input, {}))
    
    session_id = "test_sess_trade_cap"
    session = first_layer.session_manager.get_or_create_session(session_id)
    session.pending_clarification = False
    session.clarification_intents = []
    session.product_clarification_needed = False
    session.turns = []
    
    # Turn 1: Generic capability request
    res = await coordinator.process_query(question="can you help me with trade data", session_id=session_id)
    assert res.get("status") == "clarification_required"
    assert any(kw in res.get("answer", "").lower() for kw in ["product", "commodity", "trade", "period", "statistics", "year", "month", "country"])
    assert session.pending_clarification is True
    assert "trade_query" in session.clarification_intents
    
    # Turn 2: User provides entity answer
    set_nlu_cache("rice", "trade_query", 0.95)
    res2 = await coordinator.process_query(question="rice", session_id=session_id)
    assert res2.get("intent") == "trade_query"
    assert res2.get("status") in ("completed", "success")
    assert session.pending_clarification is False



@pytest.mark.asyncio
async def test_pure_meta_small_talk():
    """Verify that pure meta capability questions route to small_talk and get answered dynamically."""
    mock_retrieval = AsyncMock()
    mock_calculator = make_mock_calculator()
    mock_trade = MagicMock()
    
    config = LLMFirstLayerConfig()
    first_layer = get_llm_first_layer_service(config)
    
    mock_llm = MagicMock()
    first_layer._get_llm_service = MagicMock(return_value=mock_llm)
    
    coordinator = ServiceCoordinator(
        retrieval_client=mock_retrieval,
        general_client=mock_retrieval,
        calculator_client=mock_calculator,
        trade_data_client=mock_trade,
        first_layer_service=first_layer,
        use_input_rewriter=True
    )
    coordinator.llm_service = mock_llm
    
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.SMALL_TALK, 0.99))
    
    mock_model_res = MagicMock()
    mock_model_res.text = "I am the GDCE ChatBot. I can assist with lookups and calculations."
    mock_llm.router.providers.get.return_value.client.models.generate_content = MagicMock(return_value=mock_model_res)
    mock_llm.router.providers.get.return_value.is_available.return_value = True
    mock_llm.is_available.return_value = True
    
    session_id = "test_sess_meta"
    res = await coordinator.process_query(question="what can you do", session_id=session_id)
    assert res.get("intent") == "small_talk"
    assert res.get("status") == "completed"
    assert "I am the GDCE ChatBot" in res.get("answer", "")


@pytest.mark.asyncio
async def test_first_turn_bare_product():
    """Verify that a first-turn bare product routes directly to hs_code_lookup and expands at dispatch time (no double prefixing)."""
    mock_retrieval = AsyncMock()
    mock_retrieval.hs_code_lookup.return_value = {"status": "success", "final_answer": "Lookup for rice", "citations": []}
    mock_retrieval.general = AsyncMock()
    
    coordinator = ServiceCoordinator(
        retrieval_client=mock_retrieval,
        general_client=mock_retrieval,
        calculator_client=make_mock_calculator(),
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.HS_CODE_LOOKUP, 0.95))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    set_nlu_cache("rice", "hs_code_lookup", 0.95)
    res = await coordinator.process_query(question="rice", session_id="test_sess_rice")
    
    # Assert query routed to HS lookup
    assert res.get("intent") == "hs_code_lookup"
    # Assert query is expanded in context.question
    assert res.get("question") == "what is hs code of rice"
    
    # Assert that hs_code_lookup was called with "rice" (which is clean_query)
    called_q = mock_retrieval.hs_code_lookup.call_args[1].get("query") or mock_retrieval.hs_code_lookup.call_args[0][0]
    assert called_q == "rice"
    assert "what is hs code of what is hs code of" not in called_q


@pytest.mark.asyncio
async def test_first_turn_bare_typo():
    """Verify that a first-turn bare greeting/typo routes to small talk (no expansion)."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=make_mock_calculator(),
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.SMALL_TALK, 0.99))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    mock_llm = MagicMock()
    mock_model_res = MagicMock()
    mock_model_res.text = "Hello!"
    mock_llm.router.providers.get.return_value.client.models.generate_content = MagicMock(return_value=mock_model_res)
    mock_llm.router.providers.get.return_value.is_available.return_value = True
    mock_llm.is_available.return_value = True
    coordinator.llm_service = mock_llm
    
    set_nlu_cache("hii", "small_talk", 0.99)
    res = await coordinator.process_query(question="hii", session_id="test_sess_hii")
    assert res.get("intent") == "small_talk"
    assert res.get("answer") == "Hello!"


@pytest.mark.asyncio
async def test_clarification_turn_small_talk_exit():
    """Verify that a small talk response during clarification triggers Small Talk Exit (clears state, answers chitchat)."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=make_mock_calculator(),
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.SMALL_TALK, 0.99))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    mock_llm = MagicMock()
    mock_model_res = MagicMock()
    mock_model_res.text = "Hello! Let me know when you want to search again."
    mock_llm.router.providers.get.return_value.client.models.generate_content = MagicMock(return_value=mock_model_res)
    mock_llm.router.providers.get.return_value.is_available.return_value = True
    mock_llm.is_available.return_value = True
    coordinator.llm_service = mock_llm
    
    # Establish pending clarification
    session = coordinator.first_layer_service.session_manager.get_or_create_session("sess_exit")
    session.pending_clarification = True
    session.clarification_intents = ["hs_code_lookup"]
    session.pending_rewritten_query = "can you help me with hs code"
    
    # Send "hii" on Turn 2
    set_nlu_cache("hii", "small_talk", 0.99)
    res = await coordinator.process_query(question="hii", session_id="sess_exit")
    
    assert res.get("intent") == "small_talk"
    assert res.get("answer") == "Hello! Let me know when you want to search again."
    # State cleared
    assert session.pending_clarification is False


@pytest.mark.asyncio
async def test_clarification_turn_bare_noun_merge():
    """Verify that a bare product noun merges directly as the entity even if its intent is classified as hs_code_lookup."""
    mock_calculator = make_mock_calculator()
    
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=mock_calculator,
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.CALCULATION, 0.95))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session = coordinator.first_layer_service.session_manager.get_or_create_session("sess_bare_noun")
    session.pending_clarification = True
    session.clarification_intents = ["calculation"]
    session.pending_rewritten_query = "help me calculate duty"
    session.turns = [{"user": "help me calculate duty", "bot": "What product?"}]
    
    # Send "rice" (which classifies as hs_code_lookup)
    set_nlu_cache("rice", "hs_code_lookup", 0.95)
    res = await coordinator.process_query(question="rice", session_id="sess_bare_noun")
    
    assert res.get("intent") == "calculation"
    assert session.pending_clarification is False
    
    called_args = mock_calculator.calculate_duty.call_args_list or mock_calculator.query.call_args_list
    assert any("rice" in str(c).lower() for c in called_args)
    assert not any("what is hs code of what is hs code of" in str(c).lower() for c in called_args)


@pytest.mark.asyncio
async def test_clarification_turn_topic_switch():
    """Verify that a high-confidence intent change triggers a Topic Switch (clears state, routes to new intent)."""
    mock_calculator = make_mock_calculator(answer="Duty is $500")
    
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=mock_calculator,
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.CALCULATION, 0.95))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session = coordinator.first_layer_service.session_manager.get_or_create_session("sess_topic")
    session.pending_clarification = True
    session.clarification_intents = ["hs_code_lookup"]
    session.pending_rewritten_query = "can you help me with hs code"
    
    # Send high-confidence topic switch
    set_nlu_cache("calculate duty on $2000 laptop", "calculation", 0.95)
    res = await coordinator.process_query(question="calculate duty on $2000 laptop", session_id="sess_topic")
    
    assert res.get("intent") == "calculation"
    assert session.pending_clarification is False
    assert res.get("answer") == "Duty is $500"


@pytest.mark.asyncio
async def test_clarification_turn_nested_ask_back():
    """Verify that a gray-zone intent change triggers a Nested Ask-Back (clears state, starts new Ask-Back)."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=make_mock_calculator(),
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.CALCULATION, 0.70))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session = coordinator.first_layer_service.session_manager.get_or_create_session("sess_nested")
    session.pending_clarification = True
    session.clarification_intents = ["hs_code_lookup"]
    session.pending_rewritten_query = "can you help me with hs code"
    
    # Send gray-zone topic switch
    set_nlu_cache("calculate import tax", "calculation", 0.70)
    res = await coordinator.process_query(question="calculate import tax", session_id="sess_nested")
    
    assert res.get("status") == "clarification_required"
    # Content check: Assert the new clarification question is calculation-flavored
    assert any(kw in res.get("answer", "").lower() for kw in ["estimate", "customs", "duty", "duties", "tax", "taxes", "cif", "value", "import", "product"])
    # New state is set up for calculation
    assert session.pending_clarification is True
    assert "calculation" in session.clarification_intents
    assert session.pending_rewritten_query == "calculate import tax"


@pytest.mark.asyncio
async def test_clarification_turn_polite_topic_switch():
    """Verify that polite mixed-signal topic switches exit clarification and route directly."""
    mock_calculator = make_mock_calculator()
    
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=mock_calculator,
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.CALCULATION, 0.90))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session = coordinator.first_layer_service.session_manager.get_or_create_session("sess_polite_topic")
    session.pending_clarification = True
    session.clarification_intents = ["hs_code_lookup"]
    session.pending_rewritten_query = "can you help me with hs code"
    
    set_nlu_cache("thanks, but calculate tax", "calculation", 0.90)
    res = await coordinator.process_query(question="thanks, but calculate tax", session_id="sess_polite_topic")
    
    assert res.get("intent") == "calculation"
    assert session.pending_clarification is False


@pytest.mark.asyncio
async def test_clarification_turn_low_confidence_topic_switch():
    """Verify that a low-confidence topic switch (e.g. 'Nah I changed my mind I want to know about hs code instead') exits pending clarification and triggers Ask-Back."""
    mock_calculator = make_mock_calculator()
    
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=mock_calculator,
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.HS_CODE_LOOKUP, 0.55))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session_id = "sess_low_conf_switch"
    session = coordinator.first_layer_service.session_manager.get_or_create_session(session_id)
    session.pending_clarification = True
    session.clarification_intents = ["calculation"]
    session.pending_rewritten_query = "help me calculate duty"
    
    # Send low-confidence topic switch
    set_nlu_cache("Nah I changed my mind I want to know about hs code instead", "hs_code_lookup", 0.55)
    res = await coordinator.process_query(
        question="Nah I changed my mind I want to know about hs code instead",
        session_id=session_id
    )
    
    assert res.get("status") == "clarification_required"
    assert any(kw in res.get("answer", "").lower() for kw in ["product", "look up", "hs code", "description", "item", "name"])
    assert session.pending_clarification is True
    assert "hs_code_lookup" in session.clarification_intents



@pytest.mark.asyncio
async def test_gray_zone_bare_noun_merge():
    """Verify that a bare noun even with gray-zone confidence bypasses nested Ask-Back and merges directly."""
    mock_calculator = make_mock_calculator()
    
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=mock_calculator,
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.CALCULATION, 0.95))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session = coordinator.first_layer_service.session_manager.get_or_create_session("sess_gray_bare")
    session.pending_clarification = True
    session.clarification_intents = ["calculation"]
    session.pending_rewritten_query = "help me calculate duty"
    session.turns = [{"user": "help me calculate duty", "bot": "What product?"}]
    
    # Send "rice" (which classifies as hs_code_lookup with gray-zone confidence 0.70)
    set_nlu_cache("rice", "hs_code_lookup", 0.70)
    res = await coordinator.process_query(question="rice", session_id="sess_gray_bare")
    
    assert res.get("intent") == "calculation"
    assert session.pending_clarification is False
    
    called_args = mock_calculator.calculate_duty.call_args_list or mock_calculator.query.call_args_list
    assert any("rice" in str(c).lower() for c in called_args)


@pytest.mark.asyncio
async def test_nested_ask_back_turn_3_resolution():
    """Verify a three-turn dialog flow where Turn 2 triggers a nested Ask-Back, and Turn 3 successfully resolves and merges against the new intent."""
    mock_calculator = make_mock_calculator()
    
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=mock_calculator,
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.CALCULATION, 0.95))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session_id = "sess_three_turns"
    session = coordinator.first_layer_service.session_manager.get_or_create_session(session_id)
    session.pending_clarification = True
    session.clarification_intents = ["hs_code_lookup"]
    session.pending_rewritten_query = "can you help me with hs code"
    
    # Turn 2: User shifts topic to "calculate import tax" (gray-zone 0.70 confidence)
    set_nlu_cache("calculate import tax", "calculation", 0.70)
    res2 = await coordinator.process_query(question="calculate import tax", session_id=session_id)
    
    assert res2.get("status") == "clarification_required"
    assert session.pending_clarification is True
    assert "calculation" in session.clarification_intents
    assert session.pending_rewritten_query == "calculate import tax"
    
    # Turn 3: User answers the calculation ask-back with potatoes and CIF value details
    set_nlu_cache("potatoes $5000 from China", "calculation", 0.95)
    res3 = await coordinator.process_query(question="potatoes $5000 from China", session_id=session_id)
    
    assert res3.get("intent") == "calculation"
    assert res3.get("status") == "completed"
    assert "Duty is $200" in res3.get("answer", "")
    assert session.pending_clarification is False
    
    # Assert merge used Turn 2 + Turn 3 values correctly
    called_q = mock_calculator.query.call_args[1].get("question") or mock_calculator.query.call_args[0][0]
    assert "potatoes" in called_q.lower()
    assert "5000" in called_q
    assert "china" in called_q.lower()


@pytest.mark.asyncio
async def test_noise_topic_switch_ignored():
    """Verify that extremely low confidence (e.g. 0.15 < 0.30) for a topic switch is treated as classifier noise and stays in clarification."""
    mock_calculator = make_mock_calculator()
    
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=mock_calculator,
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session_id = "sess_noise_ignored"
    session = coordinator.first_layer_service.session_manager.get_or_create_session(session_id)
    session.pending_clarification = True
    session.clarification_intents = ["calculation"]
    session.pending_rewritten_query = "help me calculate duty"
    session.turns = [{"user": "help me calculate duty", "bot": "What product?"}]
    
    # Send classifier noise with conf 0.15
    set_nlu_cache("laptop", "hs_code_lookup", 0.15)
    res = await coordinator.process_query(question="laptop", session_id=session_id)
    
    # Conf 0.15 < 0.30 noise is ignored -> stays in calculation clarification and merges laptop
    assert res.get("intent") == "calculation"
    assert session.pending_clarification is False


@pytest.mark.asyncio
async def test_topic_switch_clears_all_spec_fields():
    """Verify that a topic switch exit resets pending_clarification, product_clarification_needed, clarification_entity, and expected_terms."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=make_mock_calculator(),
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.HS_CODE_LOOKUP, 0.55))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session_id = "sess_spec_reset"
    session = coordinator.first_layer_service.session_manager.get_or_create_session(session_id)
    session.pending_clarification = True
    session.clarification_intents = ["calculation"]
    session.pending_rewritten_query = "help me calculate duty"
    
    # Pollute spec clarification state fields
    session.product_clarification_needed = True
    session.clarification_entity = "stale car"
    session.clarification_expected_terms = ["engine", "cbu"]
    
    set_nlu_cache("Nah I changed my mind I want to know about hs code instead", "hs_code_lookup", 0.55)
    res = await coordinator.process_query(
        question="Nah I changed my mind I want to know about hs code instead",
        session_id=session_id
    )
    
    # Assert topic switch happened and ALL spec fields were cleared
    assert res.get("status") == "clarification_required"
    assert session.product_clarification_needed is False
    assert session.clarification_entity is None
    assert session.clarification_expected_terms == []


@pytest.mark.asyncio
async def test_threshold_boundary_seams():
    """Verify behavior at exact threshold boundaries: 0.299 (noise), 0.30 (low-conf exit), 0.599 (low-conf exit), 0.60 (nested ask-back), 0.799 (nested ask-back), 0.80 (high-conf exit)."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=make_mock_calculator(),
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    coordinator.workflow_executor.detect_intent_with_confidence = MagicMock(return_value=(WorkflowIntent.HS_CODE_LOOKUP, 0.55))
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    # Seam 1: 0.299 -> Noise protection (stays in clarification)
    s1 = coordinator.first_layer_service.session_manager.get_or_create_session("s_0299")
    s1.pending_clarification = True
    s1.clarification_intents = ["calculation"]
    s1.turns = [{"user": "help me calculate duty", "bot": "What product?"}]
    set_nlu_cache("rice", "hs_code_lookup", 0.299)
    res_0299 = await coordinator.process_query(question="rice", session_id="s_0299")
    assert res_0299.get("intent") == "calculation"
    assert s1.pending_clarification is False
    
    # Seam 2: 0.30 -> Low-confidence topic switch exit (triggers Ask-Back)
    s2 = coordinator.first_layer_service.session_manager.get_or_create_session("s_030")
    s2.pending_clarification = True
    s2.clarification_intents = ["calculation"]
    set_nlu_cache("hs code for rice", "hs_code_lookup", 0.30)
    res_030 = await coordinator.process_query(question="hs code for rice", session_id="s_030")
    assert res_030.get("status") == "clarification_required"
    
    # Seam 3: 0.599 -> Low-confidence topic switch exit (triggers Ask-Back)
    s3 = coordinator.first_layer_service.session_manager.get_or_create_session("s_0599")
    s3.pending_clarification = True
    s3.clarification_intents = ["calculation"]
    set_nlu_cache("hs code for rice", "hs_code_lookup", 0.599)
    res_0599 = await coordinator.process_query(question="hs code for rice", session_id="s_0599")
    assert res_0599.get("status") == "clarification_required"
    
    # Seam 4: 0.60 -> Medium confidence (nested Ask-Back)
    s4 = coordinator.first_layer_service.session_manager.get_or_create_session("s_060")
    s4.pending_clarification = True
    s4.clarification_intents = ["calculation"]
    set_nlu_cache("hs code for rice", "hs_code_lookup", 0.60)
    res_060 = await coordinator.process_query(question="hs code for rice", session_id="s_060")
    assert res_060.get("status") == "clarification_required"
    assert "hs_code_lookup" in s4.clarification_intents
    
    # Seam 5: 0.799 -> Medium confidence (nested Ask-Back, does not exit to completed)
    s5 = coordinator.first_layer_service.session_manager.get_or_create_session("s_0799")
    s5.pending_clarification = True
    s5.clarification_intents = ["calculation"]
    set_nlu_cache("hs code for rice", "hs_code_lookup", 0.799)
    res_0799 = await coordinator.process_query(question="hs code for rice", session_id="s_0799")
    assert res_0799.get("status") == "clarification_required"
    assert "hs_code_lookup" in s5.clarification_intents
    
    # Seam 6: 0.80 -> High confidence (direct exit)
    s6 = coordinator.first_layer_service.session_manager.get_or_create_session("s_080")
    s6.pending_clarification = True
    s6.clarification_intents = ["calculation"]
    set_nlu_cache("calculate duty on $2000 laptop", "calculation", 0.80)
    res_080 = await coordinator.process_query(question="calculate duty on $2000 laptop", session_id="s_080")
    assert res_080.get("intent") == "calculation"
    assert s6.pending_clarification is False


def test_resolve_from_user_response_terse_switch_and_multi_candidate():
    """Verify resolve_from_user_response behavior for terse switches ('tariff?', 'just hs'), calculation counter-signals, and multi-candidate resolution."""
    svc = get_llm_first_layer_service(LLMFirstLayerConfig()).ask_back_service
    
    # 1. Single candidate ["calculation"] with terse HS switch ("tariff?") -> returns None (prevents false calc merge)
    assert svc.resolve_from_user_response("tariff?", ["calculation"]) is None
    assert svc.resolve_from_user_response("just hs", ["calculation"]) is None
    
    # 2. Calculation answer containing "tariff" ("calculate the tariff on 5 units at $20 each", "the tariff is for 5 units at $20 each") -> returns "calculation"
    assert svc.resolve_from_user_response("calculate the tariff on 5 units at $20 each", ["calculation"]) == "calculation"
    assert svc.resolve_from_user_response("the tariff is for 5 units at $20 each", ["calculation"]) == "calculation"
    
    # 3. Multi-candidate resolution
    candidates = ["hs_code_lookup", "calculation"]
    assert svc.resolve_from_user_response("I want hs code", candidates) == "hs_code_lookup"
    assert svc.resolve_from_user_response("calculate tax", candidates) == "calculation"
    assert svc.resolve_from_user_response("option 1", candidates) == "hs_code_lookup"
    assert svc.resolve_from_user_response("option 2", candidates) == "calculation"


@pytest.mark.asyncio
async def test_nested_ask_back_clears_stale_spec_fields():
    """Verify that triggering the 0.60 <= conf < 0.80 nested Ask-Back path clears old spec clarification state."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=make_mock_calculator(),
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    
    validator = get_validator()
    validator.validate_input_full_async = AsyncMock(return_value=ValidationResult.in_scope())
    
    session_id = "sess_nested_spec_reset"
    session = coordinator.first_layer_service.session_manager.get_or_create_session(session_id)
    session.pending_clarification = True
    session.clarification_intents = ["calculation"]
    session.pending_rewritten_query = "help me calculate duty"
    
    # Pollute spec clarification state fields
    session.product_clarification_needed = True
    session.clarification_entity = "stale car"
    session.clarification_expected_terms = ["engine", "cbu"]
    
    # Trigger nested Ask-Back with conf 0.70
    set_nlu_cache("hs code for rice", "hs_code_lookup", 0.70)
    res = await coordinator.process_query(question="hs code for rice", session_id=session_id)
    
    assert res.get("status") == "clarification_required"
    assert "hs_code_lookup" in session.clarification_intents
    # Assert old spec state from abandoned calculation turn was wiped
    assert session.product_clarification_needed is False
    assert session.clarification_entity is None
    assert session.clarification_expected_terms == []


@pytest.mark.asyncio
async def test_state_isolation_between_ask_back_and_product_spec():
    """Verify that sessions in Ask-Back vs Product-Spec clarification states isolate correctly."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=make_mock_calculator(),
        trade_data_client=MagicMock(),
        first_layer_service=get_llm_first_layer_service(LLMFirstLayerConfig()),
        use_input_rewriter=True
    )
    
    session_id_ab = "sess_isolation_ask_back"
    session_ab = coordinator.first_layer_service.session_manager.get_or_create_session(session_id_ab)
    session_ab.pending_clarification = True
    session_ab.clarification_intents = ["calculation", "hs_code_lookup"]
    session_ab.pending_rewritten_query = "bmw car"
    
    session_id_ps = "sess_isolation_product_spec"
    session_ps = coordinator.first_layer_service.session_manager.get_or_create_session(session_id_ps)
    session_ps.product_clarification_needed = True
    session_ps.clarification_entity = "bmw car"
    session_ps.clarification_last_query = "bmw car"
    session_ps.clarification_expected_terms = ["cc", "convertible"]
    
    assert session_ab.is_awaiting_clarification() is True
    assert session_ps.is_awaiting_clarification() is False
    assert getattr(session_ps, "product_clarification_needed", False) is True




