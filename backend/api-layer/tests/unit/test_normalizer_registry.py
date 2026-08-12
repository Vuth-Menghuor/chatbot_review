from __future__ import annotations

from app.services.normalizers.calculator.normalizer import CalculatorNormalizer
from app.services.normalizers.fallback import FallbackNormalizer, normalize_service_name
from app.services.normalizers.registry import NormalizerRegistry
from app.services.normalizers.retrieval import RetrievalNormalizer
from app.services.normalizers.trade import TradeNormalizer


# This file protects the minimal service-routing layer before adding more service normalizers later.


# The registry must pick calculator-specific logic before falling back to generic service detection.
def test_registry_selects_calculator_normalizer_first():
    registry = NormalizerRegistry(normalizers=[CalculatorNormalizer(), TradeNormalizer(), RetrievalNormalizer()], fallback=FallbackNormalizer())

    assert registry.normalize({"calculator_result": {"summary": {"total_tax": 1}}}) == "calculator"


# The fallback normalizer keeps non-calculator payloads labeled without requiring dedicated normalizers yet.
def test_registry_uses_fallback_for_known_non_calculator_service():
    registry = NormalizerRegistry(normalizers=[CalculatorNormalizer(), TradeNormalizer(), RetrievalNormalizer()], fallback=FallbackNormalizer())

    assert registry.normalize({"service": "general", "answer": "General answer."}) == "general"


# Unknown payloads must be explicit so future routing gaps are visible in responses and logs.
def test_registry_fallback_returns_unknown_without_service_hints():
    registry = NormalizerRegistry(normalizers=[CalculatorNormalizer(), TradeNormalizer(), RetrievalNormalizer()], fallback=FallbackNormalizer())

    assert registry.normalize({"answer": "Plain answer."}) == "unknown"


# Trade is the second real normalizer, proving registry routing works beyond calculator.
def test_registry_selects_trade_normalizer_before_fallback():
    registry = NormalizerRegistry(normalizers=[CalculatorNormalizer(), TradeNormalizer(), RetrievalNormalizer()], fallback=FallbackNormalizer())

    assert registry.normalize({"trade_result": {"top_export_partners": [{"partner_country": "Vietnam"}]}}) == "trade"


# Retrieval is the third real normalizer and should route before fallback.
def test_registry_selects_retrieval_normalizer_before_fallback():
    registry = NormalizerRegistry(normalizers=[CalculatorNormalizer(), TradeNormalizer(), RetrievalNormalizer()], fallback=FallbackNormalizer())

    assert registry.normalize({"retrieval_result": {"documents": [{"title": "Import Guide"}]}}) == "retrieval"


def test_registry_maps_retrieval_related_intents_to_retrieval_service():
    registry = NormalizerRegistry(normalizers=[CalculatorNormalizer(), TradeNormalizer(), RetrievalNormalizer()], fallback=FallbackNormalizer())

    for intent in ("hs_code_lookup", "customs_qa", "document_lookup", "regulation_lookup", "retrieval", "rag", "search"):
        assert registry.normalize({"intent": intent, "answer": "Retrieval answer."}) == "retrieval"


def test_registry_keeps_unsupported_intent_as_unknown_service():
    registry = NormalizerRegistry(normalizers=[CalculatorNormalizer(), TradeNormalizer(), RetrievalNormalizer()], fallback=FallbackNormalizer())

    assert registry.normalize({"intent": "unsupported_future_intent", "answer": "Plain answer."}) == "unknown"


def test_registry_maps_trade_and_calculator_intents_without_changing_intent_value():
    registry = NormalizerRegistry(normalizers=[CalculatorNormalizer(), TradeNormalizer(), RetrievalNormalizer()], fallback=FallbackNormalizer())

    assert registry.normalize({"intent": "trade_query", "answer": "Trade answer."}) == "trade"
    assert registry.normalize({"intent": "trade_statistics", "answer": "Trade answer."}) == "trade"
    assert registry.normalize({"intent": "trade_lookup", "answer": "Trade answer."}) == "trade"
    assert registry.normalize({"intent": "tax_calculation", "answer": "Calculator answer."}) == "calculator"
    assert registry.normalize({"intent": "import_tax_calculation", "answer": "Calculator answer."}) == "calculator"


def test_normalize_service_name_maps_trade_aliases_and_intents_to_trade():
    assert normalize_service_name("trade") == "trade"
    assert normalize_service_name("trade_service") == "trade"
    assert normalize_service_name("trade_data") == "trade"
    assert normalize_service_name("trade_query") == "trade"
    assert normalize_service_name("trade_statistics") == "trade"
