"""GDCE Trade Query Service — Core Enrichment and Orchestration Pipeline Stages.

Keeps Stage 2 (Semantic Enrichment) and Stage 4 (Query Orchestration) functions strictly separated.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional

from .countries import COUNTRY_TO_CODE_MAP, VALID_COUNTRY_CODES
from .query_plan import RawQueryPlan, EnrichedQueryPlan, ScopedQueryPlan, FinalQueryPlan
from .semantic_registry import (
    normalize_intent,
    find_dimension_by_synonym,
    find_measure_by_synonym,
    SEMANTIC_REGISTRY,
    STRUCTURE_REGISTRY,
)


logger = logging.getLogger(__name__)


# ===========================================================================
# STAGE 2 — SEMANTIC ENRICHMENT
# ===========================================================================

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
    resolved["sitc_section"] = None
    resolved["sitc_division"] = None

    prod = raw_plan.raw_product
    if prod:
        prod_str = str(prod).strip()
        if prod_str.isdigit():
            if len(prod_str) == 2:
                resolved["hs_chapter"] = prod_str
            else:
                resolved["hs_code"] = prod_str
        else:
            from .product_resolver import resolve_product_to_hs
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


# ===========================================================================
# STAGE 4 — QUERY ORCHESTRATION
# ===========================================================================


def apply_cambodia_perspective(scoped_plan: ScopedQueryPlan, filters: Dict[str, Any]) -> None:
    """Enforce base country constraints and map partner countries."""
    # Deduce partner country from origin/destination
    if scoped_plan.partner_countries:
        clean_partners = [c for c in scoped_plan.partner_countries if c != "KH"]
        if clean_partners:
            if len(clean_partners) == 1:
                filters["PARTNER_COUNTRY"] = clean_partners[0]
            else:
                filters["PARTNER_COUNTRY"] = clean_partners
    else:
        origin = scoped_plan.origin_country
        dest = scoped_plan.destination_country
        partner = None
        if origin == "KH" and dest and dest != "KH":
            partner = dest
        elif dest == "KH" and origin and origin != "KH":
            partner = origin
        else:
            partner = dest or origin

        if partner and partner != "KH":
            filters["PARTNER_COUNTRY"] = partner


def build_groupings(scoped_plan: ScopedQueryPlan) -> tuple[list[str], list[str]]:
    """Clean up and build dimensions and group-by list (filtering out time fields)."""
    time_keys = {"PERIOD", "FREQ", "FREQUENCY"}
    dimensions_list = [d for d in scoped_plan.dimensions if d.upper() not in time_keys]
    group_by_list = [g for g in scoped_plan.group_by if g.upper() not in time_keys]

    if not dimensions_list:
        dimensions_list = ["FLOW"] if scoped_plan.intent in ("trend", "summary", "trade_balance") else ["PARTNER_COUNTRY"]
    if not group_by_list:
        group_by_list = ["FLOW"] if scoped_plan.intent in ("trend", "summary", "trade_balance") else ["PARTNER_COUNTRY"]

    return dimensions_list, group_by_list


def orchestrate_query_plan(scoped_plan: ScopedQueryPlan) -> FinalQueryPlan:
    """Stage 4 Query Orchestration entrypoint.

    Translates a ScopedQueryPlan with locked constraints into the finalized structures of a
    FinalQueryPlan.
    """
    filters: Dict[str, Any] = {}

    # 1. Flow
    if scoped_plan.trade_direction:
        filters["FLOW"] = scoped_plan.trade_direction

    # 2. Cambodia perspective
    apply_cambodia_perspective(scoped_plan, filters)

    # 3. Commodity codes
    if scoped_plan.hs_chapter:
        filters["HS_CHAPTER"] = scoped_plan.hs_chapter
    if scoped_plan.hs_code:
        if len(scoped_plan.hs_code) == 4:
            filters["HS_HEADING"] = scoped_plan.hs_code
        else:
            filters["HS_CODE"] = scoped_plan.hs_code

    if scoped_plan.sitc_section:
        filters["SITC_SECTION"] = scoped_plan.sitc_section
    if scoped_plan.sitc_division:
        filters["SITC_DIVISION"] = scoped_plan.sitc_division

    # 4. Mode of Transport
    if scoped_plan.mode_of_transport:
        filters["MODE_OF_TRANSPORT"] = scoped_plan.mode_of_transport

    # 5. Time periods formatting
    period: Optional[str] = None
    start_period: Optional[str] = scoped_plan.start_period
    end_period: Optional[str] = scoped_plan.end_period
    frequency: Optional[str] = scoped_plan.frequency

    # Apply frequency default for range queries
    from ..handlers.strategies import STRATEGIES
    strategy = STRATEGIES.get(scoped_plan.intent)
    default_frequency = strategy.default_frequency if strategy else None

    if (start_period or end_period) and not frequency:
        frequency = default_frequency or "A"
        logger.info(f"[orchestrate_query_plan] Range query has no frequency. Defaulting to '{frequency}'.")

    # If start_period or end_period are specified, they should be normalized to correct frequency sub-periods
    if start_period or end_period:
        if not frequency:
            frequency = default_frequency or "A"
        
        # Normalize 4-digit years to correct frequency start/end periods
        if frequency == "S":
            if start_period and len(start_period) == 4:
                start_period = f"{start_period}-S1"
            if end_period and len(end_period) == 4:
                end_period = f"{end_period}-S2"
        elif frequency == "Q":
            if start_period and len(start_period) == 4:
                start_period = f"{start_period}-Q1"
            if end_period and len(end_period) == 4:
                end_period = f"{end_period}-Q4"
        elif frequency == "M":
            if start_period and len(start_period) == 4:
                start_period = f"{start_period}-01"
            if end_period and len(end_period) == 4:
                end_period = f"{end_period}-12"
        
        # Range query takes precedence over year-constructed period
        period = None
        resolved_freq = frequency
    else:
        resolved_freq = None
        if scoped_plan.year is not None:
            year_text = str(scoped_plan.year)
            if scoped_plan.quarter:
                period = f"{year_text}-{scoped_plan.quarter}"
                resolved_freq = "Q"
            elif scoped_plan.semester is not None:
                semester_text = str(scoped_plan.semester)
                period = f"{year_text}-S{semester_text}"
                resolved_freq = "S"
            elif scoped_plan.month is not None:
                month_text = str(scoped_plan.month).zfill(2)
                period = f"{year_text}-{month_text}"
                resolved_freq = "M"
            elif frequency == "S":
                # Unspecified semester under frequency S queries both semesters
                start_period = f"{year_text}-S1"
                end_period = f"{year_text}-S2"
                period = None
                resolved_freq = "S"
            else:
                period = year_text
                resolved_freq = "A"

    if not frequency:
        frequency = default_frequency or resolved_freq

    import datetime
    # Fallback: if no time context at all, default to last complete year
    if not period and not start_period and not end_period:
        default_year = datetime.datetime.now().year - 1
        period = str(default_year)
        if not frequency:
            frequency = "A"
        logger.info(f"[orchestrate_query_plan] No period specified. Defaulting to {period} (Annual).")

    # 6. Sorting formatting
    sort: Optional[str] = None
    sort_metric = scoped_plan.sort_metric
    sort_order = scoped_plan.sort_order

    if not sort_metric and strategy and strategy.default_sort:
        default_metric, default_order = strategy.default_sort.split(":")
        sort_metric = default_metric
        if not sort_order:
            sort_order = default_order

    if sort_metric:
        if sort_order == "asc":
            sort = f"{sort_metric}:asc"
        elif sort_order == "desc" or scoped_plan.intent == "ranking" or not sort_order:
            sort = f"{sort_metric}:desc"

    # Substitute VALUE_KHR with VALUE_USD (Problem 4)
    clean_metrics = []
    for m in scoped_plan.metrics:
        if m == "VALUE_KHR":
            logger.warning("VALUE_KHR requested but not available in dataset. Substituting VALUE_USD.")
            if "VALUE_USD" not in clean_metrics:
                clean_metrics.append("VALUE_USD")
        else:
            clean_metrics.append(m)

    # 7. Groupings
    dimensions_list, group_by_list = build_groupings(scoped_plan)

    return FinalQueryPlan(
        intent=scoped_plan.intent,
        version=scoped_plan.version,
        filters=filters,
        metrics=clean_metrics,
        group_by=group_by_list,
        dimensions=dimensions_list,
        period=period,
        start_period=start_period,
        end_period=end_period,
        frequency=frequency,
        sort=sort,
        limit=scoped_plan.limit,
        offset=scoped_plan.offset,
    )


# ===========================================================================
# BACKWARD COMPATIBILITY ONLY
# ===========================================================================

def convert_legacy_params(raw_params: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible helper mapping input dict params through Stage 2 -> 3 -> 4 pipeline.

    Returns the formatted FinalQueryPlan as a flat dictionary.
    """
    from .query_plan import RawQueryPlan
    from ..handlers.scopes import apply_intent_scoping

    raw_plan = RawQueryPlan(
        intent=raw_params.get("intent", "summary"),
        raw_origin_country=raw_params.get("origin_country"),
        raw_destination_country=raw_params.get("destination_country"),
        raw_partner_countries=raw_params.get("partner_countries"),
        raw_trade_direction=raw_params.get("trade_direction"),
        raw_product=raw_params.get("hs_code") or raw_params.get("hs_chapter") or raw_params.get("product"),
        raw_mode_of_transport=raw_params.get("mode_of_transport"),
        raw_year=raw_params.get("year"),
        raw_years=raw_params.get("years"),
        raw_month=raw_params.get("month"),
        raw_quarter=raw_params.get("quarter"),
        raw_semester=raw_params.get("semester"),
        raw_start_period=raw_params.get("start_period"),
        raw_end_period=raw_params.get("end_period"),
        raw_frequency=raw_params.get("frequency"),
        raw_group_by=raw_params.get("group_by"),
        raw_dimensions=raw_params.get("dimensions"),
        raw_metrics=raw_params.get("metrics"),
        raw_sort_order=raw_params.get("sort_order"),
        raw_sort_metric=raw_params.get("sort_metric"),
        raw_limit=raw_params.get("limit"),
        raw_offset=raw_params.get("offset"),
        version=raw_params.get("version", "trade_volume_1.0"),
        question=raw_params.get("question"),
    )

    enriched = enrich_query_plan(raw_plan)
    scoped = apply_intent_scoping(enriched)
    final = orchestrate_query_plan(scoped)

    res = {
        "intent": final.intent,
        "version": final.version,
        "filters": final.filters,
        "metrics": final.metrics,
        "group_by": scoped.group_by,
        "dimensions": scoped.dimensions,
        "period": final.period,
        "start_period": final.start_period,
        "end_period": final.end_period,
        "frequency": final.frequency,
        "sort": final.sort,
        "limit": final.limit,
        "offset": final.offset,
        "origin_country": scoped.origin_country,
        "destination_country": scoped.destination_country,
        "sort_order": scoped.sort_order,
        "sort_metric": scoped.sort_metric,
        "year": scoped.year,
        "years": scoped.years,
        "month": scoped.month,
        "quarter": scoped.quarter,
        "semester": scoped.semester,
    }
    
    # Flatten fields for compatibility with legacy test assertions
    res["trade_direction"] = final.filters.get("FLOW")
    res["partner_countries"] = final.filters.get("PARTNER_COUNTRY") if isinstance(final.filters.get("PARTNER_COUNTRY"), list) else None
    res["partner_country"] = final.filters.get("PARTNER_COUNTRY") if isinstance(final.filters.get("PARTNER_COUNTRY"), str) else None
    res["mode_of_transport"] = final.filters.get("MODE_OF_TRANSPORT")
    res["hs_code"] = final.filters.get("HS_HEADING") or final.filters.get("HS_CODE")
    res["hs_chapter"] = final.filters.get("HS_CHAPTER")
    res["sitc_section"] = final.filters.get("SITC_SECTION")
    res["sitc_division"] = final.filters.get("SITC_DIVISION")
    return res
