"""Unit tests for service coordinator"""

import pytest
from unittest.mock import AsyncMock

from ..core import ServiceCoordinator
from ..infrastructure.cache_service import get_cache_service


class DummyLLMService:
    def __init__(self, intent="definition", selection=None):
        self.intent = intent
        self.selection = selection or {
            "selected_code": None,
            "confidence": 0.0,
            "reason": "No selection",
            "index": -1,
        }

    def classify_intent(self, question):
        return self.intent, 0.95, "test intent"

    async def select_best_hs_code(self, query, candidates):
        return self.selection

    async def rewrite_descriptions_batch(self, candidates):
        return candidates

    async def rewrite_input(self, user_input, context=None, intent_hint=None):
        return user_input, {
            "rewrite_reason": "not_needed",
            "confidence": 1.0,
            "rewritten": False,
        }

    def is_available(self) -> bool:
        return True


@pytest.mark.asyncio
class TestServiceCoordinator:
    """Test ServiceCoordinator class."""

    async def test_process_definition_query(self, coordinator):
        """Test processing a definition query."""
        response = await coordinator.process_query(
            question="What is an HS code?"
        )

        assert response["status"] == "completed"
        assert response["intent"] == "definition"
        assert "request_id" in response
        assert response["question"] == "What is an HS code?"

    async def test_process_calculation_query(self, coordinator):
        """Test processing a calculation query."""
        response = await coordinator.process_query(
            question="Calculate the import tax on 100 USD of electronics"
        )

        # Should either complete or need clarification
        assert response["status"] in ["completed", "clarification_required"]
        assert response["intent"] == "calculation"

    async def test_calculation_query_routes_directly_to_calculator_query(self):
        """Calculation queries should bypass local HS lookup and direct parameters, calling query() instead."""
        get_cache_service().invalidate_cache()

        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock()

        calculator_client = AsyncMock()
        calculator_client.query = AsyncMock(return_value={
            "status": "success",
            "total": 1234,
            "currency": "KHR",
            "breakdown": {},
            "line_items": [],
            "assumptions": [
                "HS Code: 0101.21.00",
                "Product: Live horses, asses, mules and hinnies. Horses.",
                "Origin: Japan",
            ],
            "references": [],
        })

        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=calculator_client,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=False,
            llm_service=DummyLLMService(
                intent="calculation"
            ),
        )

        response = await coordinator.process_query(
            question="Calculate import duty for living horses CIF 80000 yen from japan"
        )

        assert response["status"] in {"completed", "failed"}
        retrieval_client.hs_code_lookup.assert_not_awaited()
        calculator_client.query.assert_awaited_once_with(
            question="Calculate import duty for living horses CIF 80000 yen from japan"
        )

    async def test_process_trade_query(self, coordinator):
        """Test processing a trade query."""
        response = await coordinator.process_query(
            question="What is the trade volume with Vietnam?"
        )

        assert response["status"] == "completed"
        assert response["intent"] == "trade_query"

    async def test_query_with_session_id(self, coordinator):
        """Test query processing with session ID."""
        session_id = "session_test_123"
        response = await coordinator.process_query(
            question="What is HS code?",
            session_id=session_id
        )

        assert response["request_id"]
        assert response["status"] == "completed"

    async def test_error_handling(self, coordinator):
        """Test error handling in coordinator."""
        # Create coordinator without clients
        critical_coordinator = ServiceCoordinator(
            retrieval_client=None,
            calculator_client=None
        )

        response = await critical_coordinator.process_query(
            question="What is HS code?"
        )

        # Should handle gracefully
        assert response["status"] in ["failed", "completed"]
        assert "request_id" in response

    async def test_hs_intent_safety_gate_routes_fee_query_to_policy(self):
        """LLM HS intent should not bypass service/fee safety routing."""
        get_cache_service().invalidate_cache()
        retrieval_client = AsyncMock()
        retrieval_client.policy_inquiry = AsyncMock(return_value={
            "documents": [
                {
                    "id": "fee_1",
                    "content": "Scanning fees are handled as customs service fees.",
                    "score": 0.91,
                }
            ],
            "status": "success",
            "answer_source": "extractive_fallback",
        })
        retrieval_client.hs_code_lookup = AsyncMock(return_value={"documents": []})

        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=None,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=False,
            llm_service=DummyLLMService(intent="hs_code_lookup"),
        )

        response = await coordinator.process_query("What is the scanning fee?")

        assert response["intent"] == "policy_query"
        retrieval_client.policy_inquiry.assert_awaited_once()
        retrieval_client.hs_code_lookup.assert_not_awaited()

    async def test_hs_intent_safety_gate_keeps_livestock_product_in_hs_lookup(self):
        """Product phrases like 'live horse' must stay on HS lookup instead of being downgraded."""
        get_cache_service().invalidate_cache()
        retrieval_client = AsyncMock()
        retrieval_client.policy_inquiry = AsyncMock(return_value={"documents": []})
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [
                {
                    "id": "0101.21.00",
                    "content": "Live horses, asses, mules and hinnies. Horses.",
                    "score": 0.99,
                    "metadata": {
                        "hs_code": "0101.21.00",
                        "description": "Live horses, asses, mules and hinnies. Horses.",
                    },
                }
            ],
            "status": "success",
            "answer_source": "mock",
        })

        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=None,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=False,
            llm_service=DummyLLMService(
                intent="hs_code_lookup",
                selection={
                    "selected_code": "0101.21.00",
                    "confidence": 0.96,
                    "reason": "Best match for live horse",
                    "index": 0,
                },
            ),
        )

        response = await coordinator.process_query("live horse")

        assert response["status"] == "completed"
        assert response["metadata"]["selected_code"] == "0101.21.00"
        retrieval_client.hs_code_lookup.assert_awaited_once()
        retrieval_client.policy_inquiry.assert_not_awaited()

    async def test_hs_selection_semantic_conflict_requires_clarification(self):
        """Final HS selection should be downgraded when it conflicts with query semantics."""
        get_cache_service().invalidate_cache()
        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [
                {
                    "id": "6203.41.00",
                    "content": "Men's or boys' trousers of wool.",
                    "score": 0.93,
                    "metadata": {
                        "hs_code": "6203.41.00",
                        "description": "Men's or boys' trousers of wool.",
                    },
                },
                {
                    "id": "6204.62.00",
                    "content": "Women's or girls' trousers of cotton.",
                    "score": 0.90,
                    "metadata": {
                        "hs_code": "6204.62.00",
                        "description": "Women's or girls' trousers of cotton.",
                    },
                },
            ],
            "status": "success",
            "answer_source": "mock",
        })

        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=None,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=False,
            llm_service=DummyLLMService(
                intent="hs_code_lookup",
                selection={
                    "selected_code": "6203.41.00",
                    "confidence": 0.92,
                    "reason": "test selection",
                    "index": 0,
                },
            ),
        )

        response = await coordinator.process_query("What is the HS code for women's woven cotton trousers?")

        assert response["status"] == "clarification_required"
        assert response["metadata"]["selected_code"] is None
        assert "conflict" in response["metadata"]["hs_validation"]
        assert "conflicts" in response["answer"].lower()

    async def test_hs_vehicle_query_uses_gemini_best_match_without_forcing_clarification(self):
        """Broad vehicle queries should return a Gemini-selected best match plus an explanation."""
        get_cache_service().invalidate_cache()
        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [
                {
                    "id": "8702.90.79",
                    "content": "Unspecified motor coaches, buses, or minibuses for transporting ten or more persons.",
                    "score": 1.0,
                    "metadata": {
                        "hs_code": "8702.90.79",
                        "description": "Unspecified motor coaches, buses, or minibuses for transporting ten or more persons.",
                    },
                },
                {
                    "id": "8702.90.32",
                    "content": "Completely Knocked Down (CKD) buses, coaches, or minibuses for 10 or more persons.",
                    "score": 0.98,
                    "metadata": {
                        "hs_code": "8702.90.32",
                        "description": "Completely Knocked Down (CKD) buses, coaches, or minibuses for 10 or more persons.",
                    },
                },
            ],
            "status": "success",
            "answer_source": "mock",
        })

        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=None,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=False,
            llm_service=DummyLLMService(
                intent="hs_code_lookup",
                selection={
                    "selected_code": "8702.90.79",
                    "confidence": 0.95,
                    "reason": "Closest general match for a bus/minibus lookup",
                    "index": 0,
                },
            ),
        )

        response = await coordinator.process_query("bus")

        assert response["status"] == "completed"
        assert response["metadata"]["selected_code"] == "8702.90.79"
        assert "why this is likely what you want" in response["answer"].lower()
        assert "gemini picked" in response["answer"].lower()

    async def test_hs_selection_confidence_is_clamped_to_probability_range(self):
        """Selection confidence should always be reported in [0.0, 1.0]."""
        get_cache_service().invalidate_cache()
        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [
                {
                    "id": "0101.29.00",
                    "content": "Other live horses.",
                    "score": 1.0,
                    "metadata": {
                        "hs_code": "0101.29.00",
                        "description": "Other live horses.",
                    },
                }
            ],
            "status": "success",
            "answer_source": "mock",
        })

        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=None,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=False,
            llm_service=DummyLLMService(
                intent="hs_code_lookup",
                selection={
                    "selected_code": "0101.29.00",
                    "confidence": 5.0,
                    "reason": "out-of-range confidence from provider",
                    "index": 0,
                },
            ),
        )

        response = await coordinator.process_query("live horses")

        assert response["status"] == "completed"
        assert response["metadata"]["selection_confidence"] == 1.0
        assert "confidence: 1.00" in response["answer"].lower()

    async def test_short_unclassified_product_query_is_rewritten_and_routed_to_hs_lookup(self):
        """Short product-only queries like 'train?' should become HS lookup requests."""
        get_cache_service().invalidate_cache()

        class ShortProductRewriteLLM(DummyLLMService):
            async def rewrite_input(self, user_input, context=None, intent_hint=None):
                if intent_hint == "hs_code_lookup" and user_input.strip().lower() == "train?":
                    return (
                        "What is the HS code for train?",
                        {
                            "rewrite_reason": "hs_short_product_auto_template",
                            "confidence": 0.98,
                            "rewritten": True,
                        },
                    )
                return await super().rewrite_input(user_input, context=context, intent_hint=intent_hint)

        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [
                {
                    "id": "8603.10.00",
                    "content": "Self-propelled railway or tramway coaches.",
                    "score": 0.95,
                    "metadata": {
                        "hs_code": "8603.10.00",
                        "description": "Self-propelled railway or tramway coaches.",
                    },
                }
            ],
            "status": "success",
            "answer_source": "mock",
        })
        retrieval_client.policy_inquiry = AsyncMock(return_value={"documents": []})

        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=None,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=True,
            llm_service=ShortProductRewriteLLM(
                intent="unclassified",
                selection={
                    "selected_code": "8603.10.00",
                    "confidence": 0.91,
                    "reason": "Best match for train product query",
                    "index": 0,
                },
            ),
        )

        response = await coordinator.process_query("train?")

        assert response["status"] == "completed"
        retrieval_client.hs_code_lookup.assert_awaited_once()
        _, kwargs = retrieval_client.hs_code_lookup.await_args
        assert kwargs["query"] == "What is the HS code for train?"
        retrieval_client.policy_inquiry.assert_not_awaited()

    async def test_short_product_query_skips_rewriter_and_routes_to_hs_lookup(self):
        """Short product lookups like 'bus?' should go directly to HS lookup without rewrite."""
        get_cache_service().invalidate_cache()

        class NoRewriteShortProductLLM(DummyLLMService):
            async def rewrite_input(self, user_input, context=None, intent_hint=None):
                raise AssertionError("rewrite_input should not be called for short HS product lookups")

        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [
                {
                    "id": "8702.10.00",
                    "content": "Motor vehicles for the transport of 10 or more persons, including the driver.",
                    "score": 0.95,
                    "metadata": {
                        "hs_code": "8702.10.00",
                        "description": "Motor vehicles for the transport of 10 or more persons, including the driver.",
                    },
                }
            ],
            "status": "success",
            "answer_source": "mock",
        })
        retrieval_client.policy_inquiry = AsyncMock(return_value={"documents": []})

        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=None,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=True,
            llm_service=NoRewriteShortProductLLM(
                intent="hs_code_lookup",
                selection={
                    "selected_code": "8702.10.00",
                    "confidence": 0.93,
                    "reason": "Short product lookups should stay on HS lookup",
                    "index": 0,
                },
            ),
        )

        response = await coordinator.process_query("bus?")

        assert response["status"] == "completed"
        retrieval_client.hs_code_lookup.assert_awaited_once()
        _, kwargs = retrieval_client.hs_code_lookup.await_args
        assert kwargs["query"] == "bus?"
        retrieval_client.policy_inquiry.assert_not_awaited()

        assert response["status"] == "completed"
        retrieval_client.hs_code_lookup.assert_awaited_once()
        _, kwargs = retrieval_client.hs_code_lookup.await_args
        assert kwargs["query"] == "bus?"
        retrieval_client.policy_inquiry.assert_not_awaited()

    async def test_hs_code_standardization(self):
        """Test that non-standard HS codes in the user query are standardized before processing."""
        from ..utils import standardize_hs_codes_in_text
        
        # 8-digit variants
        assert standardize_hs_codes_in_text("01012100") == "0101.21.00"
        assert standardize_hs_codes_in_text("0101.2100") == "0101.21.00"
        assert standardize_hs_codes_in_text("010121.00") == "0101.21.00"
        assert standardize_hs_codes_in_text("0101 21 00") == "0101.21.00"
        assert standardize_hs_codes_in_text("0101-21-00") == "0101.21.00"
        assert standardize_hs_codes_in_text("0101.21.00") == "0101.21.00"
        
        # 6-digit variants
        assert standardize_hs_codes_in_text("010121") == "0101.21"
        assert standardize_hs_codes_in_text("0101.21") == "0101.21"
        assert standardize_hs_codes_in_text("0101 21") == "0101.21"
        
        # Edge cases & exclusions
        assert standardize_hs_codes_in_text("CIF 500000") == "CIF 500000"
        assert standardize_hs_codes_in_text("value is $100000") == "value is $100000"
        assert standardize_hs_codes_in_text("year 2026") == "year 2026"

    async def test_coordinator_process_query_standardizes_hs_code(self):
        """Verify the coordinator standardizes the query before routing to downstream clients."""
        get_cache_service().invalidate_cache()
        retrieval_client = AsyncMock()
        retrieval_client.hs_code_lookup = AsyncMock(return_value={
            "documents": [
                {
                    "id": "0101.21.00",
                    "content": "Live horses, asses, mules and hinnies. Horses.",
                    "score": 0.99,
                    "metadata": {
                        "hs_code": "0101.21.00",
                        "description": "Live horses, asses, mules and hinnies. Horses.",
                    },
                }
            ],
            "hs_validation": {
                "status": "valid",
                "primary_code": "0101.21.00",
                "candidates": [],
            },
            "status": "success",
            "answer_source": "mock",
        })
        
        coordinator = ServiceCoordinator(
            retrieval_client=retrieval_client,
            calculator_client=None,
            trade_data_client=None,
            use_llm_intent=False,
            use_input_rewriter=False,
            llm_service=DummyLLMService(
                intent="hs_code_lookup",
                selection={
                    "selected_code": "0101.21.00",
                    "confidence": 0.96,
                    "reason": "Test match",
                    "index": 0,
                },
            ),
        )
        
        # Test input 01012100 (unstandardized)
        response = await coordinator.process_query("What is the duty rate for 01012100?")
        
        assert response["status"] == "completed"
        retrieval_client.hs_code_lookup.assert_awaited_once()
        _, kwargs = retrieval_client.hs_code_lookup.await_args
        assert kwargs["query"] == "What is the duty rate for 0101.21.00?"

    async def test_process_small_talk_query(self, coordinator):
        """Test processing of small-talk greeting queries."""
        response = await coordinator.process_query(
            question="Hii"
        )
        assert response["status"] == "completed"
        assert response["intent"] == "small_talk"
        assert "Hello!" in response["answer"]