"""GDCE Trade Query Service — Stage 2 (Semantic Enrichment) Functions."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from app.core.countries import COUNTRY_TO_CODE_MAP, VALID_COUNTRY_CODES
from app.core.semantic_registry import (
    SEMANTIC_REGISTRY,
    STRUCTURE_REGISTRY,
    find_dimension_by_synonym,
    find_measure_by_synonym,
    normalize_intent,
)
from app.schemas.query_plan import EnrichedQueryPlan, RawQueryPlan

logger = logging.getLogger(__name__)


def resolve_dimension_value(dimension: str, value_text: Any) -> Any:
    """Map dynamic text value(s) to a dimension code (e.g. 'export' -> 'EX', or ['air', 'sea'] -> ['4', '1'])."""
    if isinstance(value_text, list):
        resolved_list = []
        for val in value_text:
            res = resolve_dimension_value_single(dimension, val)
            if res:
                resolved_list.append(res)
        return resolved_list if resolved_list else None
    else:
        return resolve_dimension_value_single(dimension, value_text)


def resolve_dimension_value_single(dimension: str, value_text: str) -> Optional[str]:
    """Map dynamic text value to a dimension code (e.g. 'export' -> 'EX')."""
    dim_code = find_dimension_by_synonym(dimension)
    if not dim_code:
        return None

    val_clean = str(value_text).strip().lower()
    struct_dim = STRUCTURE_REGISTRY.get(dim_code)
    sem_dim = SEMANTIC_REGISTRY.get(dim_code)

    if not sem_dim or not struct_dim:
        return None

    # Check exact code match if structured values exist
    if struct_dim.values:
        for val in struct_dim.values:
            if val.lower() == val_clean:
                return val

    # Check semantic synonyms values mapping
    for canonical_val, synonyms in sem_dim.values_map.items():
        if val_clean == canonical_val.lower() or val_clean in synonyms:
            return canonical_val

    return None


def resolve_country(country_text: Optional[str]) -> Optional[str]:
    """Map dynamic country text (e.g. "China", "vietnam") to ISO-2 country code."""
    if not country_text:
        return None

    country_clean = country_text.strip().upper()
    if country_clean in VALID_COUNTRY_CODES:
        return country_clean

    # Run through the COUNTRY_TO_CODE_MAP pattern registry
    for pattern, code in COUNTRY_TO_CODE_MAP.items():
        if re.search(pattern, country_text, re.IGNORECASE):
            return code

    return None


def resolve_dimensions(raw_plan: RawQueryPlan) -> Dict[str, Any]:
    """Resolve dimensions, measures, and sorting fields to canonical terms."""
    resolved: Dict[str, Any] = {}

    # 1. Resolve Group By list
    if raw_plan.raw_group_by is not None:
        resolved["group_by"] = [
            find_dimension_by_synonym(g) or g for g in raw_plan.raw_group_by
        ]
    else:
        resolved["group_by"] = None

    # 2. Resolve Dimensions list
    if raw_plan.raw_dimensions is not None:
        resolved["dimensions"] = [
            find_dimension_by_synonym(d) or d for d in raw_plan.raw_dimensions
        ]
    else:
        resolved["dimensions"] = None

    # 3. Resolve Metrics list
    if raw_plan.raw_metrics is not None:
        resolved["metrics"] = [
            find_measure_by_synonym(m) or m for m in raw_plan.raw_metrics
        ]
    else:
        resolved["metrics"] = None

    # 4. Resolve Sort Metric
    if raw_plan.raw_sort_metric:
        resolved["sort_metric"] = find_measure_by_synonym(raw_plan.raw_sort_metric) or raw_plan.raw_sort_metric
    else:
        resolved["sort_metric"] = None

    return resolved


def resolve_entities(raw_plan: RawQueryPlan) -> Dict[str, Any]:
    """Resolve entity codes (ISO-2 country, Mode of Transport, Trade Flow/Direction, and Product HS)."""
    resolved: Dict[str, Any] = {}

    # 1. Countries resolution
    resolved["origin_country"] = resolve_country(raw_plan.raw_origin_country)
    resolved["destination_country"] = resolve_country(raw_plan.raw_destination_country)

    if raw_plan.raw_partner_countries is not None:
        resolved["partner_countries"] = [
            resolve_country(c) or c for c in raw_plan.raw_partner_countries
        ]
    else:
        resolved["partner_countries"] = None

    # 2. Trade flow (direction) mapping
    if raw_plan.raw_trade_direction:
        resolved["trade_direction"] = resolve_dimension_value("FLOW", raw_plan.raw_trade_direction)
    else:
        resolved["trade_direction"] = None

    # 3. Mode of transport mapping
    if raw_plan.raw_mode_of_transport:
        resolved["mode_of_transport"] = resolve_dimension_value("MODE_OF_TRANSPORT", raw_plan.raw_mode_of_transport)
    else:
        resolved["mode_of_transport"] = None

    # 4. Product / HS resolving
    resolved["hs_code"] = None
    resolved["hs_chapter"] = None
    resolved["sitc_section"] = raw_plan.raw_sitc_section
    resolved["sitc_division"] = raw_plan.raw_sitc_division

    prod = raw_plan.raw_product
    if prod:
        prod_str = str(prod).strip()
        if prod_str.isdigit():
            if len(prod_str) == 2:
                resolved["hs_chapter"] = prod_str
            else:
                resolved["hs_code"] = prod_str
        else:
            from app.core.product_resolver import resolve_product_to_hs
            resolved_hs = resolve_product_to_hs(prod_str)
            if resolved_hs:
                if len(resolved_hs) == 2:
                    resolved["hs_chapter"] = resolved_hs
                else:
                    resolved["hs_code"] = resolved_hs
            else:
                resolved["hs_code"] = prod_str

    return resolved


def enrich_query_plan(raw_plan: RawQueryPlan) -> EnrichedQueryPlan:
    """Stage 2: Main Entrypoint for Semantic Enrichment.

    Transforms raw text tags in RawQueryPlan to canonical terms/codes, producing EnrichedQueryPlan.
    """
    intent_normalized = normalize_intent(raw_plan.intent)

    dims = resolve_dimensions(raw_plan)
    entities = resolve_entities(raw_plan)

    # Classification preference suggestion (HS vs SITC)
    # Check if user explicitly queries economic divisions or sectors
    query_text_indicator = []
    if raw_plan.raw_product:
        query_text_indicator.append(raw_plan.raw_product.lower())
    if raw_plan.raw_group_by:
        query_text_indicator.extend([g.lower() for g in raw_plan.raw_group_by])

    hs_vs_sitc_suggestion = "HS"
    for text in query_text_indicator:
        if any(term in text for term in ["sector", "economic", "sitc", "division", "industry"]):
            hs_vs_sitc_suggestion = "SITC"
            break

    year = raw_plan.raw_year
    years = raw_plan.raw_years
    if year is None and isinstance(years, list) and len(years) == 1:
        year = years[0]

    return EnrichedQueryPlan(
        intent=intent_normalized,
        origin_country=entities["origin_country"],
        destination_country=entities["destination_country"],
        partner_countries=entities["partner_countries"],
        trade_direction=entities["trade_direction"],
        hs_code=entities["hs_code"],
        hs_chapter=entities["hs_chapter"],
        sitc_section=entities["sitc_section"],
        sitc_division=entities["sitc_division"],
        mode_of_transport=entities["mode_of_transport"],
        year=year,
        years=years,
        month=raw_plan.raw_month,
        quarter=raw_plan.raw_quarter,
        semester=raw_plan.raw_semester,
        start_period=raw_plan.raw_start_period,
        end_period=raw_plan.raw_end_period,
        frequency=raw_plan.raw_frequency,
        group_by=dims["group_by"],
        dimensions=dims["dimensions"],
        metrics=dims["metrics"],
        sort_order=raw_plan.raw_sort_order,
        sort_metric=dims["sort_metric"],
        limit=raw_plan.raw_limit,
        offset=raw_plan.raw_offset,
        version=raw_plan.version,
        hs_vs_sitc_suggestion=hs_vs_sitc_suggestion,
    )
