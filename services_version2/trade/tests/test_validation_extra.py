"""Extra unit tests for parameter extraction and handler logic."""

import pytest

pytestmark = pytest.mark.integration

from services_version2.trade.core.service import extract_parameters

def test_extract_parameters_trended_last_3_years():
    params = extract_parameters("How have Cambodia's exports to China trended over the last 3 years?")
    assert params["intent"] == "trend"
    assert params["origin_country"] == "KH"
    assert params["destination_country"] == "CN"
    assert params["trade_direction"] == "EX"
    assert "start_period" in params
    assert "end_period" in params
    assert int(params["end_period"]) >= int(params["start_period"])
    assert (int(params["end_period"]) - int(params["start_period"]) + 1) == 3

def test_extract_parameters_bottom_20_ranking():
    params = extract_parameters("Show me the bottom 20 partner countries by trade value.")
    assert params["intent"] == "ranking"
    assert params.get("limit") == 20
    assert params.get("sort_order") == "asc"

def test_extract_parameters_trend_hs_code_no_grouping():
    params = extract_parameters("Show me the monthly import trend for HS Code 8517 in 2025.")
    assert params["intent"] == "trend"
    assert params.get("hs_code") == "8517"
    # Allow optional time groupings that might be extracted by the LLM
    if "group_by" in params:
        assert params["group_by"] == ["PERIOD"]
    if "dimensions" in params:
        assert params["dimensions"] == ["PERIOD"]

def test_extract_parameters_quarterly_frequency():
    params = extract_parameters("What is the quarterly trade balance trend for 2024?")
    assert params["intent"] in ("trend", "trade_balance")
    assert (params.get("year") == 2024 or 
            params.get("period") == "2024" or 
            params.get("start_period") == "2024" or 
            params.get("end_period") == "2024")
    assert params.get("frequency") == "Q"

def test_convert_legacy_params_respects_sort_order():
    from services_version2.trade.core.enrichment import convert_legacy_params
    params = {
        "intent": "ranking",
        "sort_order": "asc",
    }
    merged = convert_legacy_params(params)
    
    assert merged["sort"] == "VALUE_USD:asc"

def test_generate_visualizations_trade_balance_aggregation():
    from services_version2.trade.visualization.chart_mapper import generate_visualizations
    rows = [
        {"PERIOD": "2025-01", "FLOW": "EX", "VALUE_USD": 1000.0},
        {"PERIOD": "2025-01", "FLOW": "IM", "VALUE_USD": 400.0},
        {"PERIOD": "2025-02", "FLOW": "EX", "VALUE_USD": 2000.0},
        {"PERIOD": "2025-02", "FLOW": "IM", "VALUE_USD": 2500.0},
    ]
    query_params = {"group_by": ["period"]}
    result = generate_visualizations(rows, intent="trade_balance", query_params=query_params)
    
    # Check table is not aggregated (remains details)
    assert len(result["table"]["rows"]) == 4
    
    # Check visualization is aggregated to 2 points
    vis = result["visualization"]
    assert vis["type"] == "bar"
    assert vis["labels"] == ["2025-01", "2025-02"]
    assert vis["datasets"][0]["data"] == [600.0, -500.0]
    assert vis["datasets"][0]["label"] == "Net Trade Balance (USD)"

def test_convert_legacy_params_preserves_partner_countries():
    from services_version2.trade.core.enrichment import convert_legacy_params
    raw_params = {
        "intent": "comparison",
        "origin_country": "KH",
        "partner_countries": ["US", "CN"],
        "trade_direction": "EX",
    }
    params = convert_legacy_params(raw_params)
    assert params["partner_countries"] == ["US", "CN"]
    assert params["origin_country"] == "KH"
    assert params["destination_country"] is None

def test_convert_legacy_params_comparison_no_countries():
    from services_version2.trade.core.enrichment import convert_legacy_params
    raw_params = {
        "intent": "comparison",
        "destination_country": "KH",
        "trade_direction": "IM",
    }
    params = convert_legacy_params(raw_params)
    assert params["partner_countries"] is None
    assert params["destination_country"] == "KH"
    assert params["origin_country"] is None

def test_convert_legacy_params_comparison_filters_out_cambodia():
    from services_version2.trade.core.enrichment import convert_legacy_params
    raw_params = {
        "intent": "comparison",
        "partner_countries": ["KH", "Cambodia", "US", "CN"],
        "trade_direction": "IM",
    }
    params = convert_legacy_params(raw_params)
    assert params["partner_countries"] == ["US", "CN"]

def test_extract_parameters_currency_khr():
    params = extract_parameters("Show me the exports to China in Khmer Riel for 2025.")
    assert "VALUE_KHR" in params.get("metrics", [])
    assert "VALUE_USD" not in params.get("metrics", [])

def test_extract_parameters_currency_usd():
    params = extract_parameters("Show me the imports from Vietnam in USD for 2024.")
    assert "VALUE_USD" in params.get("metrics", [])
    assert "VALUE_KHR" not in params.get("metrics", [])

def test_extract_parameters_semester_range():
    params = extract_parameters("Show trade trend of electronics from S1 2024 to S2 2024")
    assert params["intent"] == "trend"
    assert params["start_period"] == "2024-S1"
    assert params["end_period"] == "2024-S2"
    assert params["frequency"] == "S"
    
    params = extract_parameters("Compare imports of garment in 2024 S1 and S2")
    assert params["intent"] == "trend"
    assert params["start_period"] == "2024-S1"
    assert params["end_period"] == "2024-S2"
    assert params["frequency"] == "S"
    
    params = extract_parameters("How did trade balance change between S1 and S2 of 2025?")
    assert params["intent"] == "trade_balance"
    assert params["start_period"] == "2025-S1"
    assert params["end_period"] == "2025-S2"
    assert params["frequency"] == "S"


def test_compare_air_vs_sea_transport():
    params = extract_parameters("Compare air freight exports to Japan against sea freight exports to Japan")
    assert params["intent"] in ("trend", "comparison")
    assert set(params["mode_of_transport"]) == {"air", "sea"}
    assert params["trade_direction"] == "EX"
    assert params["partner_country"] == "JP"
    
    # Check filters mapping in convert_legacy_params
    from services_version2.trade.core.enrichment import convert_legacy_params
    legacy_transformed = convert_legacy_params({
        "intent": "trend",
        "trade_direction": "export",
        "mode_of_transport": ["air", "sea"],
        "partner_countries": ["JP"]
    })
    assert legacy_transformed["intent"] == "trend"
    assert legacy_transformed["trade_direction"] == "EX"
    assert legacy_transformed["partner_country"] == "JP"
    assert set(legacy_transformed["filters"]["MODE_OF_TRANSPORT"]) == {"4", "1"}
