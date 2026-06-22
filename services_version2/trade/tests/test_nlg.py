import pytest
from services_version2.trade.core.nlg.formatters import extract_facts
from services_version2.trade.core.nlg.suggestions import get_suggestions
from services_version2.trade.core.nlg.generator import _generate_fallback_template

def test_extract_facts_summary():
    payload = {
        "summary": {
            "total_trade_value": 192223348.85,
            "currency": "USD"
        },
        "records": [
            {"FLOW": "IM", "VALUE_USD": 192223348.85, "NET_WEIGHT": 150000.0}
        ]
    }
    query_params = {
        "intent": "summary",
        "trade_direction": "IM",
        "partner_country": "JP",
        "mode_of_transport": "1",
        "period": "2026-Q1"
    }
    
    facts = extract_facts(payload, query_params)
    assert facts["intent"] == "summary"
    assert facts["flow"] == "import"
    assert facts["partner_country"] == "Japan"
    assert facts["mode_of_transport"] == "sea"
    assert facts["period"] == "2026-Q1"
    assert facts["total_trade_value_usd"] == 192223348.85
    assert facts["total_weight_kg"] == 150000.0

def test_extract_facts_comparison():
    payload = {
        "records": [
            {"PARTNER_COUNTRY": "US", "VALUE_USD": 100000.0},
            {"PARTNER_COUNTRY": "CN", "VALUE_USD": 200000.0}
        ]
    }
    query_params = {
        "intent": "comparison",
        "period": "2025"
    }
    
    facts = extract_facts(payload, query_params)
    assert facts["intent"] == "comparison"
    assert len(facts["comparison_records"]) == 2
    assert facts["comparison_records"][0]["country"] == "United States"
    assert facts["comparison_records"][0]["trade_value_usd"] == 100000.0

def test_get_suggestions():
    facts = {
        "intent": "summary",
        "flow": "export",
        "partner_country": "Japan",
        "period": "2025"
    }
    suggestions = get_suggestions(facts, {})
    assert len(suggestions) == 3
    assert any("trend" in s.lower() for s in suggestions)
    assert any("products" in s.lower() for s in suggestions)

def test_fallback_templates():
    facts = {
        "intent": "summary",
        "flow": "import",
        "partner_country": "Japan",
        "period": "2026-Q1",
        "mode_of_transport": "sea",
        "total_trade_value_usd": 192223348.85
    }
    msg = _generate_fallback_template(facts)
    assert "Imports" in msg
    assert "Japan" in msg
    assert "$192.22 million" in msg
    assert "2026-Q1" in msg
