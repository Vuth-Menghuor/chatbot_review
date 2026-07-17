import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.suggestion_service import SuggestionService
from app.services.session_context import SessionContext
from app.services.coordinator import ServiceCoordinator, WorkflowIntent
from app.services.workflow import WorkflowStatus, WorkflowContext


# Verify that suggestions are generated during active clarification (no longer suppressed).

@pytest.mark.asyncio
async def test_coordinator_generates_suggestions_during_clarification():
    """Clarification in progress should still yield suggestions."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=MagicMock(),
        trade_data_client=MagicMock(),
        use_input_rewriter=True,
    )

    session = SessionContext(session_id="sess_1")
    session.product_clarification_needed = True

    context = WorkflowContext(request_id="req1", question="car", session_id="sess_1")
    context.session_context = session
    context.intent = WorkflowIntent.HS_CODE_LOOKUP
    context.status = WorkflowStatus.COMPLETED
    context.set_result("retrieval", {"final_answer": "Do you mean electric car?"})

    response = await coordinator._build_response(context)
    assert len(response.get("suggestions", [])) > 0


# Complex scenarios: SuggestionService

def test_suggestion_service_case_insensitive_intent_matching():
    """A current_intent with inconsistent casing must still match the YAML mapping."""
    service = SuggestionService()

    suggestions_mixed = service.get_suggestions(
        current_intent="HS_Code_Lookup",  # classifier emits inconsistent casing
        rewritten_query="electric car"
    )
    suggestions_lower = service.get_suggestions(
        current_intent="hs_code_lookup",
        rewritten_query="electric car"
    )

    assert suggestions_mixed == suggestions_lower
    assert len(suggestions_mixed) > 0


def test_suggestion_service_non_string_entity_from_extract_entity():
    """extract_entity() returning a non-string (e.g. dict/list) must not crash,
    and should degrade to the fallback path rather than raise."""
    service = SuggestionService()

    with patch("app.services.suggestion_service.extract_entity", return_value={"name": "car", "type": "vehicle"}):
        suggestions = service.get_suggestions(
            current_intent="hs_code_lookup",
            rewritten_query="what about this vehicle"
        )

    # Should not raise, and should fall back to generic fallbacks since
    # the malformed entity is coerced to "" by _safe_str.
    assert suggestions == service.generic_fallbacks[:3]


def test_suggestion_service_non_string_last_entity_from_session():
    """session_context.last_entity being a non-string object must not crash."""
    service = SuggestionService()

    session = MagicMock()
    session.last_entity = {"unexpected": "object"}

    with patch("app.services.suggestion_service.extract_entity", return_value=None):
        suggestions = service.get_suggestions(
            current_intent="hs_code_lookup",
            rewritten_query="what about it",
            session_context=session
        )

    assert suggestions == service.generic_fallbacks[:3]


def test_suggestion_service_entity_priority_current_over_session():
    """Current turn's extracted entity must take priority over stale session last_entity."""
    service = SuggestionService()

    session = MagicMock()
    session.last_entity = "rice"  # stale, from a previous turn

    with patch("app.services.suggestion_service.extract_entity", return_value="car"):
        suggestions = service.get_suggestions(
            current_intent="hs_code_lookup",
            rewritten_query="what is the tax for car",
            session_context=session
        )

    assert any("car" in s.lower() for s in suggestions)
    assert not any("rice" in s.lower() for s in suggestions)


def test_suggestion_service_unmapped_intent_routes_to_fallback():
    """An intent not present in intent_adjacency.yaml (e.g. 'general') must
    route straight to generic_fallbacks, never attempt template hydration."""
    service = SuggestionService()

    suggestions = service.get_suggestions(
        current_intent="general",
        rewritten_query="tell me about electric car"
    )

    assert suggestions == service.generic_fallbacks[:3]
    # None of the fallback strings should have been templated with an entity
    for s in suggestions:
        assert "{entity}" not in s


def test_suggestion_service_minimum_count_padding():
    """If template filtering strips suggestions below MIN_SUGGESTIONS, the
    service must top up from generic_fallbacks rather than returning 0-1."""
    service = SuggestionService()

    # Force every templated suggestion to collide with the current query so
    # the filter strips all of them, forcing the padding path.
    original_adjacency = service.intent_adjacency.get("hs_code_lookup", [])
    if not original_adjacency:
        pytest.skip("hs_code_lookup not present in loaded YAML")

    with patch.object(service, "intent_adjacency", {
        "hs_code_lookup": [
            {"text": "duplicate query text for car", "intent": "calculation"},
            {"text": "duplicate query text for car", "intent": "trade_query"},
        ]
    }):
        suggestions = service.get_suggestions(
            current_intent="hs_code_lookup",
            rewritten_query="duplicate query text for car"  # matches both templates
        )

    assert len(suggestions) >= 2
    # Padding should have come from generic_fallbacks since both templates
    # collided with the query and were filtered out.
    assert any(s in service.generic_fallbacks for s in suggestions)


def test_suggestion_service_import_procedure_intent_present():
    """import_procedure must be a valid key with suggestions pointing to the
    other three core intents, matching the mentor's original ask."""
    service = SuggestionService()

    if "import_procedure" not in service.intent_adjacency:
        pytest.skip("import_procedure not yet added to intent_adjacency.yaml")

    suggestions = service.get_suggestions(
        current_intent="import_procedure",
        rewritten_query="car"
    )
    assert len(suggestions) > 0
    for s in suggestions:
        assert "car" in s.lower()


# Complex scenarios: Coordinator integration

@pytest.mark.asyncio
async def test_coordinator_suppresses_suggestions_on_unclassified():
    """unclassified intent must suppress suggestions."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=MagicMock(),
        trade_data_client=MagicMock(),
        use_input_rewriter=True,
    )

    context = WorkflowContext(request_id="req3", question="???", session_id="sess_3")
    context.intent = WorkflowIntent.UNCLASSIFIED
    context.status = WorkflowStatus.COMPLETED

    response = await coordinator._build_response(context)
    assert response.get("suggestions", []) == []


@pytest.mark.asyncio
async def test_coordinator_suppresses_suggestions_on_small_talk():
    """small_talk intent must suppress suggestions."""
    coordinator = ServiceCoordinator(
        retrieval_client=AsyncMock(),
        general_client=AsyncMock(),
        calculator_client=MagicMock(),
        trade_data_client=MagicMock(),
        use_input_rewriter=True,
    )

    context = WorkflowContext(request_id="req4", question="hello", session_id="sess_4")
    context.intent = WorkflowIntent.SMALL_TALK
    context.status = WorkflowStatus.COMPLETED

    response = await coordinator._build_response(context)
    assert response.get("suggestions", []) == []


@pytest.mark.asyncio
async def test_coordinator_suggestion_failure_does_not_break_response():
    """If SuggestionService.get_suggestions raises, the coordinator must fail
    silently to an empty list rather than propagating the exception and
    breaking the primary answer response."""
    mock_retrieval = AsyncMock()
    mock_retrieval.hs_code_lookup = AsyncMock(return_value={
        "is_generic": False,
        "final_answer": "HS Code 8703 covers electric cars.",
        "documents": [{"id": "doc1", "content": "car data", "score": 0.9}]
    })

    coordinator = ServiceCoordinator(
        retrieval_client=mock_retrieval,
        general_client=mock_retrieval,
        calculator_client=MagicMock(),
        trade_data_client=MagicMock(),
        use_input_rewriter=True,
    )
    coordinator.workflow_executor = MagicMock()
    coordinator.workflow_executor.cleanup_query = lambda q: q.strip()

    # Force the suggestion service to blow up
    coordinator.suggestion_service.get_suggestions = MagicMock(side_effect=RuntimeError("boom"))

    context = WorkflowContext(
        request_id="req5",
        question="what is the hs code of electric car",
        session_id="session_5",
        original_input="what is the hs code of electric car"
    )
    context.intent = WorkflowIntent.HS_CODE_LOOKUP
    context.status = WorkflowStatus.COMPLETED
    context.set_result("retrieval", mock_retrieval.hs_code_lookup.return_value)

    # Must not raise
    response = await coordinator._build_response(context)

    assert response.get("suggestions", []) == []
    # Primary answer must still be intact despite the suggestion failure
    assert "final_answer" in str(response) or response.get("answer")


@pytest.mark.asyncio
async def test_coordinator_suggestions_reflect_multi_turn_entity_carryover():
    """A follow-up turn with no new entity should still hydrate suggestions
    using the entity carried over in session_context.last_entity."""
    mock_retrieval = AsyncMock()
    mock_retrieval.calculation = AsyncMock(return_value={
        "final_answer": "The import tax is 15%.",
    })

    coordinator = ServiceCoordinator(
        retrieval_client=mock_retrieval,
        general_client=mock_retrieval,
        calculator_client=MagicMock(),
        trade_data_client=MagicMock(),
        use_input_rewriter=True,
    )
    coordinator.workflow_executor = MagicMock()
    coordinator.workflow_executor.cleanup_query = lambda q: q.strip()

    session = SessionContext(session_id="sess_6")
    session.last_entity = "electric car"  # carried over from a prior turn

    context = WorkflowContext(
        request_id="req6",
        question="how much tax",  # no entity mentioned this turn
        session_id="sess_6",
        original_input="how much tax"
    )
    context.session_context = session
    context.intent = WorkflowIntent.CALCULATION
    context.status = WorkflowStatus.COMPLETED
    context.set_result("retrieval", mock_retrieval.calculation.return_value)

    with patch("app.services.suggestion_service.extract_entity", return_value=None):
        response = await coordinator._build_response(context)

    assert len(response.get("suggestions", [])) > 0
    assert any("electric car" in s.lower() for s in response["suggestions"])


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))