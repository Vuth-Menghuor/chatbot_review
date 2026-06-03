"""Regression tests for short product-only HS lookup queries."""

from ..llm_first_layer.shims.validator_service import get_input_validator
# pyrefly: ignore [missing-import]
from ..core.llm_intent_detector import LLMIntentDetector, WorkflowIntent


def test_short_product_query_is_in_scope():
    validator = get_input_validator()

    is_valid, reason = validator.validate_input("Bus")

    assert is_valid is True
    assert reason is None


def test_short_product_phrase_routes_to_hs_lookup():
    detector = LLMIntentDetector(timeout=1)

    intent, confidence, reasoning = detector.detect_intent("live horse")

    assert intent == WorkflowIntent.HS_CODE_LOOKUP
    assert confidence >= 0.9
    assert "product description" in reasoning.lower()