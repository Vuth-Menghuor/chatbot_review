"""Unit tests for Semantic Metadata Registry, validation warnings, and serialization."""

import json
import pytest

from services_version2.trade.core.exceptions import ValidationError
from services_version2.trade.core.semantic_registry import (
    STRUCTURE_REGISTRY,
    normalize_intent,
    find_dimension_by_synonym,
    find_measure_by_synonym,
    get_parent_dimension,
    get_children_dimensions,
)
from services_version2.trade.core.enrichment import (
    resolve_dimension_value,
    enrich_query_plan,
    orchestrate_query_plan,
    convert_legacy_params,
)
from services_version2.trade.handlers.scopes import apply_intent_scoping
from services_version2.trade.core.validation import validate_query_plan, validate_extracted_parameters
from services_version2.trade.core.query_plan import (
    RawQueryPlan,
    EnrichedQueryPlan,
    ScopedQueryPlan,
    FinalQueryPlan,
)
from services_version2.trade.dal.dal_request_builder import DALRequestBuilder


def test_normalize_intent():
    assert normalize_intent("trends") == "trend"
    assert normalize_intent("comparisons") == "comparison"
    assert normalize_intent("growth analysis") == "growth"
    assert normalize_intent("trade balance") == "trade_balance"
    assert normalize_intent("summary") == "summary"


def test_find_dimension_by_synonym():
    assert find_dimension_by_synonym("trade_direction") == "FLOW"
    assert find_dimension_by_synonym("economic_sector") == "SITC_SECTION"
    assert find_dimension_by_synonym("mot") == "MODE_OF_TRANSPORT"
    assert find_dimension_by_synonym("invalid_synonym") is None


def test_find_measure_by_synonym():
    assert find_measure_by_synonym("trade value") == "VALUE_USD"
    assert find_measure_by_synonym("riel") == "VALUE_KHR"
    assert find_measure_by_synonym("net weight") == "NET_WEIGHT"
    assert find_measure_by_synonym("invalid_measure") is None


def test_resolve_dimension_value():
    assert resolve_dimension_value("FLOW", "export") == "EX"
    assert resolve_dimension_value("FLOW", "exports") == "EX"
    assert resolve_dimension_value("FLOW", "inbound trade") == "IM"
    assert resolve_dimension_value("MODE_OF_TRANSPORT", "air") == "4"
    assert resolve_dimension_value("MODE_OF_TRANSPORT", "sea") == "1"


def test_convert_legacy_params():
    raw = {
        "intent": "trends",
        "trade_direction": "export",
        "mode_of_transport": "air",
        "group_by": ["trade_direction", "economic_sector"],
    }
    transformed = convert_legacy_params(raw)
    assert transformed["intent"] == "trend"
    assert transformed["trade_direction"] == "EX"
    assert transformed["mode_of_transport"] == "4"
    assert transformed["group_by"] == ["FLOW", "SITC_SECTION"]


def test_validate_extracted_parameters_valid():
    params = {
        "intent": "summary",
        "metrics": ["VALUE_USD", "NET_WEIGHT"],
        "dimensions": ["FLOW", "PARTNER_COUNTRY"],
        "trade_direction": "EX",
        "mode_of_transport": "4",
        "hs_code": "1234",
    }
    # Should not raise an exception
    validate_extracted_parameters(params)


def test_validate_extracted_parameters_invalid_intent():
    params = {"intent": "invalid_intent"}
    with pytest.raises(ValidationError) as exc:
        validate_extracted_parameters(params)
    assert "Unknown intent" in str(exc.value)


def test_validate_extracted_parameters_unsupported_measure():
    params = {"metrics": ["INVALID_METRIC"]}
    with pytest.raises(ValidationError) as exc:
        validate_extracted_parameters(params)
    assert "Unsupported measure" in str(exc.value)


def test_validate_extracted_parameters_value_khr_fallback():
    params = {"metrics": ["VALUE_KHR"]}
    with pytest.raises(ValidationError) as exc:
        validate_extracted_parameters(params)
    
    error_msg = str(exc.value)
    # Parse the warning suggestion output
    payload = json.loads(error_msg)
    assert payload["warning"] == "VALUE_KHR not available"
    assert payload["fallback_suggested"] == "VALUE_USD"


def test_dal_request_builder_serialization():
    builder = DALRequestBuilder()
    params = {
        "intent": "summary",
        "partner_country": "CN",
        "trade_direction": "EX",
        "hs_code": "1006",
        "group_by": ["FLOW", "PERIOD"],  # Period should be filtered out
    }
    req = builder.build_request("summary", params)
    
    assert req.intent == "summary"
    assert req.filters["PARTNER_COUNTRY"] == "CN"
    assert req.filters["FLOW"] == "EX"
    assert req.filters["HS_HEADING"] == "1006"
    assert req.group_by == ["FLOW"]  # PERIOD filtered out
    assert req.dimensions == ["FLOW"]


def test_validate_extracted_parameters_unsupported_version():
    params = {
        "intent": "summary",
        "version": "invalid_dataset_version",
    }
    with pytest.raises(ValidationError) as exc:
        validate_extracted_parameters(params)
    assert "Unknown dataset version" in str(exc.value)


def test_validate_extracted_parameters_dataset_bound():
    params = {
        "intent": "summary",
        "version": "trade_volume_1.0",
        "metrics": ["VALUE_USD"],
        "dimensions": ["FLOW"],
    }
    # Should not raise exception
    validate_extracted_parameters(params)


def test_structure_descriptions_exist():
    assert STRUCTURE_REGISTRY["HS_CHAPTER"].description == "Top-level HS commodity classification (2-digit)"
    assert STRUCTURE_REGISTRY["VALUE_USD"].description == "Trade value in United States Dollars"
    assert STRUCTURE_REGISTRY["PERIOD"].description == "Time period of the data point, formatted according to the frequency"


def test_query_plan_lifecycle_transitions():
    # 1. Stage 1 (Raw Plan)
    raw = RawQueryPlan(
        intent="trends",
        raw_trade_direction="export",
        raw_origin_country="Cambodia",
        raw_destination_country="China",
        raw_product="rice",
        raw_year=2024,
    )
    assert raw.intent == "trends"
    assert raw.raw_trade_direction == "export"

    # 2. Stage 2 (Enriched Plan)
    enriched = enrich_query_plan(raw)
    assert enriched.intent == "trend"
    assert enriched.trade_direction == "EX"
    assert enriched.origin_country == "KH"
    assert enriched.destination_country == "CN"
    assert enriched.hs_code == "1006"  # rice maps to 1006
    assert enriched.hs_vs_sitc_suggestion == "HS"

    # 3. Stage 3 (Scoped Plan)
    scoped = apply_intent_scoping(enriched)
    # Check Cambodia-centric flows (exporter is KH, destination is CN, trade direction is EX -> remains EX)
    assert scoped.trade_direction == "EX"
    assert scoped.origin_country == "KH"
    assert scoped.destination_country == "CN"
    # Check metrics defaulted
    assert "VALUE_USD" in scoped.metrics
    # Locked to HS
    assert scoped.hs_code == "1006"
    assert scoped.sitc_section is None

    # 4. Stage 4 (Final Plan)
    final = orchestrate_query_plan(scoped)
    assert final.filters["FLOW"] == "EX"
    assert final.filters["PARTNER_COUNTRY"] == "CN"
    assert final.filters["HS_HEADING"] == "1006"
    assert final.period == "2024"
    assert final.frequency == "M"

    # 5. Stage 5 (Validation & Serialization)
    validate_query_plan(final)
    builder = DALRequestBuilder()
    req = builder.build_from_plan(final)
    assert req.intent == "trend"
    assert req.filters["FLOW"] == "EX"
    assert req.filters["PARTNER_COUNTRY"] == "CN"


def test_total_trade_query_filters_out_kh_partner():
    raw = RawQueryPlan(
        intent="summary",
        raw_trade_direction="export",
        raw_origin_country="Cambodia",
        raw_year=2025,
    )
    enriched = enrich_query_plan(raw)
    scoped = apply_intent_scoping(enriched)
    final = orchestrate_query_plan(scoped)
    
    assert "PARTNER_COUNTRY" not in final.filters
    assert final.filters["FLOW"] == "EX"


def test_hierarchy_helpers():
    # HS chapter -> heading hierarchy check
    assert get_parent_dimension("HS_HEADING") == "HS_CHAPTER"
    assert get_parent_dimension("HS_CHAPTER") is None
    assert get_children_dimensions("HS_CHAPTER") == ["HS_HEADING"]
    
    # SITC section -> division hierarchy check
    assert get_parent_dimension("SITC_DIVISION") == "SITC_SECTION"
    assert get_children_dimensions("SITC_SECTION") == ["SITC_DIVISION"]




