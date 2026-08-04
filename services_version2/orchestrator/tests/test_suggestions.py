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
    assert len(response.get("suggestion", [])) > 0


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
    en_fallbacks = service.generic_fallbacks.get("en", []) if isinstance(service.generic_fallbacks, dict) else service.generic_fallbacks
    assert suggestions == en_fallbacks[:3]


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

    en_fallbacks = service.generic_fallbacks.get("en", []) if isinstance(service.generic_fallbacks, dict) else service.generic_fallbacks
    assert suggestions == en_fallbacks[:3]


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

    en_fallbacks = service.generic_fallbacks.get("en", []) if isinstance(service.generic_fallbacks, dict) else service.generic_fallbacks
    assert suggestions == en_fallbacks[:3]
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
    en_fallbacks = service.generic_fallbacks.get("en", []) if isinstance(service.generic_fallbacks, dict) else service.generic_fallbacks
    assert any(s in en_fallbacks for s in suggestions)


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
    assert response.get("suggestion", []) == []


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
    assert response.get("suggestion", []) == []


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

    assert response.get("suggestion", []) == []
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

    assert len(response.get("suggestion", [])) > 0
    assert any("electric car" in s.lower() for s in response["suggestion"])


def test_suggestion_service_parameter_noise_sanitization():
    """Complex calculation queries with key-value parameters must not yield parameter math noise in chips."""
    service = SuggestionService()

    suggestions = service.get_suggestions(
        current_intent="calculation",
        rewritten_query="import tax pls — hs 8703.24.00, cif=40000usd, china, acfta, dv=0, dq 40%"
    )

    assert len(suggestions) >= 2
    for s in suggestions:
        assert "=" not in s
        assert "pls" not in s.lower()
        assert "dq" not in s.lower()
        assert "cif=" not in s.lower()


def test_suggestion_service_no_hs_lookup_chip_for_calculation_intent():
    """Calculation intent must NOT suggest HS code lookup — the user already provided the HS code.
    Instead it should suggest procedure/trade adjacent follow-ups."""
    from app.utils.entity_utils import extract_entity

    query = "hi how much tax if i import a car hs 8703.22.00 cif is $10500, from china, ACFTA rate, dv=0"
    entity = extract_entity(query)
    assert entity == "car", f"Expected 'car', got '{entity}'"

    service = SuggestionService()
    suggestions = service.get_suggestions(
        current_intent="calculation",
        rewritten_query=query,
    )

    assert len(suggestions) >= 2
    for s in suggestions:
        assert "hs code for" not in s.lower(), f"Unexpected hs_code_lookup chip: '{s}'"
        assert "=" not in s


def test_suggestion_service_calculation_product_description_from_result_payload():
    """When query has no explicit product name but calculation result contains assumptions with product description,
    suggestions must hydrate with the product description (e.g. General merchandise) instead of query noise."""
    from app.utils.entity_utils import extract_entity

    query = "need tax calc for hs code 8703.24.00, cif $40,000, importing from china"
    extracted = extract_entity(query)
    # The raw query has no product noun (only HS code & financial parameters), so extract_entity yields None
    assert extracted is None, f"Expected None for query with no product name, got '{extracted}'"

    service = SuggestionService()
    result_payload = {
        "assumptions": [
            "+ HS Code: 8703.24.00",
            "+ Product: General merchandise",
            "+ Origin country: CN"
        ]
    }

    suggestions = service.get_suggestions(
        current_intent="calculation",
        rewritten_query=query,
        result_payload=result_payload
    )

    assert len(suggestions) >= 2
    assert not any("need calc for 000" in s.lower() for s in suggestions), f"Bogus noise entity in suggestions: {suggestions}"
    assert any("General merchandise" in s for s in suggestions), f"Expected 'General merchandise' in suggestions, got {suggestions}"


def test_suggestion_service_calculation_extracts_product_from_answer_header():
    """For queries like 'can u calculate tax for 8703.22.00 china cif10500usd acfta dv 0',
    suggestions must extract entity from PRODUCT INFORMATION: * HS Code: 8703.22.00 (General merchandise)."""
    query = "can u calculate tax for 8703.22.00 china cif10500usd acfta dv 0"
    service = SuggestionService()
    result_payload = {
        "answer": (
            "PRODUCT INFORMATION:\n"
            "* HS Code: 8703.22.00 (General merchandise)\n"
            "* Origin Country: CN\n"
        )
    }

    suggestions = service.get_suggestions(
        current_intent="calculation",
        rewritten_query=query,
        result_payload=result_payload
    )

    assert len(suggestions) >= 2
    assert not any("can u calculate" in s.lower() for s in suggestions), f"Bogus noise entity in suggestions: {suggestions}"
    assert any("General merchandise" in s for s in suggestions), f"Expected 'General merchandise' in suggestions, got {suggestions}"


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))