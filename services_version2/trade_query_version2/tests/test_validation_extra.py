"""Extra unit tests for parameter extraction and handler logic."""

import pytest
from services_version2.trade_query_version2.core.validation import extract_parameters
from services_version2.trade_query_version2.handlers.base import BaseHandler
from services_version2.trade_query_version2.handlers.strategies import STRATEGIES

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
    assert "group_by" not in params
    assert "dimensions" not in params

def test_extract_parameters_quarterly_frequency():
    params = extract_parameters("What is the quarterly trade balance trend for 2024?")
    assert params["intent"] == "trend"
    assert params.get("year") == 2024
    assert params.get("frequency") == "Q"

def test_handler_merge_strategy_defaults_respects_sort_order():
    handler = BaseHandler(dal_client=None, request_builder=None)
    params = {
        "intent": "ranking",
        "sort_order": "asc",
    }
    strategy = STRATEGIES["ranking"]
    merged = handler._merge_strategy_defaults(params, strategy)
    
    assert merged["sort"] == "VALUE_USD:asc"
