"""GDCE Trade Query Service — Stage 4 (Query Orchestration) Functions."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.schemas.query_plan import FinalQueryPlan, ScopedQueryPlan

logger = logging.getLogger(__name__)


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
    if scoped_plan.quarter:
        frequency = "Q"
    elif scoped_plan.semester is not None:
        frequency = "S"
    elif scoped_plan.month is not None:
        frequency = "M"

    # Apply frequency default for range queries
    from app.registry.strategies import STRATEGIES
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

        # Convert full-year ranges to a single period to avoid DAL bugs when combining range filters with FLOW filters
        is_full_year_range = False
        if start_period and end_period and len(start_period) >= 7 and len(end_period) >= 7:
            s_yr, s_sub = start_period[:4], start_period[5:7]
            e_yr, e_sub = end_period[:4], end_period[5:7]
            if s_yr == e_yr:
                if frequency == "M" and s_sub == "01" and e_sub == "12":
                    is_full_year_range = True
                elif frequency == "Q" and s_sub == "Q1" and e_sub == "Q4":
                    is_full_year_range = True
                elif frequency == "S" and s_sub == "S1" and e_sub == "S2":
                    is_full_year_range = True

        if is_full_year_range and start_period:
            period = start_period[:4]
            start_period = None
            end_period = None
            resolved_freq = frequency
        else:
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

    import datetime
    current_year = datetime.datetime.now().year

    if not frequency:
        frequency = default_frequency or resolved_freq

    # Fallback: if no time context at all, default to the current year.
    # Even if the year is still in progress, the user is asking "now" — NLG will
    # label it as YTD via the is_current_year_partial flag below.
    if not period and not start_period and not end_period:
        period = str(current_year)
        if not frequency:
            frequency = "A"
        scoped_plan_extra_defaulted = True
        logger.info(f"[orchestrate_query_plan] No period specified. Defaulting to current year {period} (Annual).")
    else:
        scoped_plan_extra_defaulted = False

    # Substitute VALUE_KHR with VALUE_USD (Problem 4)
    clean_metrics = []
    for m in scoped_plan.metrics:
        if m == "VALUE_KHR":
            logger.warning("VALUE_KHR requested but not available in dataset. Substituting VALUE_USD.")
            if "VALUE_USD" not in clean_metrics:
                clean_metrics.append("VALUE_USD")
        else:
            clean_metrics.append(m)

    # 6. Sorting formatting
    sort: Optional[str] = None
    sort_metric = scoped_plan.sort_metric
    sort_order = scoped_plan.sort_order

    if not sort_metric and strategy and strategy.default_sort:
        default_metric, default_order = strategy.default_sort.split(":")
        sort_metric = default_metric
        if not sort_order:
            sort_order = default_order

    # Section 23 Extended: Sort Parameter Metric Alignment (Universal)
    if sort_metric and clean_metrics:
        if sort_metric not in clean_metrics:
            found_match = False
            for m in clean_metrics:
                if m.upper() == sort_metric.upper():
                    sort_metric = m
                    found_match = True
                    break
            if not found_match:
                if "WEIGHT" in sort_metric.upper():
                    weight_metric = next((m for m in clean_metrics if "WEIGHT" in m.upper()), None)
                    if weight_metric:
                        sort_metric = weight_metric
                    else:
                        sort_metric = clean_metrics[0]
                else:
                    value_metric = next((m for m in clean_metrics if "USD" in m.upper() or "KHR" in m.upper()), None)
                    if value_metric:
                        sort_metric = value_metric
                    else:
                        sort_metric = clean_metrics[0]

    if sort_metric:
        if sort_order == "asc":
            sort = f"{sort_metric}:asc"
        elif sort_order == "desc" or scoped_plan.intent == "ranking" or not sort_order:
            sort = f"{sort_metric}:desc"

    # 7. Groupings
    dimensions_list, group_by_list = build_groupings(scoped_plan)

    # Section 25: Redundant group_by/dimensions Dimension Cleanup
    single_value_filter_keys = set()
    for k, v in filters.items():
        if not isinstance(v, list) and v is not None:
            single_value_filter_keys.add(k.upper())

    cleaned_group_by = []
    for g in group_by_list:
        if g.upper() in single_value_filter_keys:
            logger.info(f"[orchestrate_query_plan] Stripped redundant group_by dimension '{g}' since it is already filtered to a single value.")
            continue
        cleaned_group_by.append(g)

    cleaned_dimensions = []
    for d in dimensions_list:
        if d.upper() in single_value_filter_keys:
            continue
        cleaned_dimensions.append(d)

    if cleaned_group_by:
        group_by_list = cleaned_group_by
    if cleaned_dimensions:
        dimensions_list = cleaned_dimensions

    # Intent Downgrade: if intent is trend but temporal params resolve to a single point, downgrade to summary
    intent = scoped_plan.intent
    if intent == "trend":
        is_single_point = False
        if period is not None:
            # If frequency is monthly/quarterly/semester but period is only a 4-digit year, it expands to multiple sub-periods
            if frequency in ("M", "Q", "S") and len(str(period)) == 4:
                is_single_point = False
            else:
                is_single_point = True
        elif start_period is not None and end_period is not None and start_period == end_period:
            is_single_point = True

        if is_single_point:
            logger.info("[orchestrate_query_plan] Intent is trend but temporal params resolve to a single point. Downgrading intent to summary.")
            intent = "summary"

    # Ranking intent flow consolidation check
    consolidate_flows = False
    original_limit = scoped_plan.limit or 100
    dal_limit = original_limit

    if intent == "ranking" and "FLOW" not in filters and "PARTNER_COUNTRY" in group_by_list:
        consolidate_flows = True
        dal_limit = 1000  # High limit to fetch all counterpart EX/IM records pre-consolidation
    elif intent == "growth":
        dal_limit = 1000  # High limit to fetch all periods for all entities to compute growth rates safely

    if intent == "ranking" and "FLOW" not in filters and "PARTNER_COUNTRY" in group_by_list:
        if "FLOW" in group_by_list:
            group_by_list.remove("FLOW")
        if "FLOW" in dimensions_list:
            dimensions_list.remove("FLOW")

    # Section 19: Growth period scope enforcement — SCOPE EXPANSION ONLY.
    # NO growth computation here. All delta math lives in normaliser.compute_growth_rates.
    if intent == "growth":
        if start_period and end_period and start_period == end_period:
            period = start_period
            start_period = None
            end_period = None

        if period is not None and start_period is None and end_period is None:
            # Single period: auto-expand to two-year range so DAL returns both baseline and comparison
            try:
                base_year = int(str(period)[:4])
                if frequency == "M":
                    # Month-over-month: expand to full 12-month series for the year
                    start_period = f"{base_year}-01"
                    end_period = f"{base_year}-12"
                    period = None
                    logger.info(f"[orchestrate_query_plan] Growth/MoM: expanded year {base_year} to full monthly range.")
                elif frequency in ("Q", "S"):
                    # Quarterly/semester: keep as-is, the sub-periods provide natural comparison
                    pass
                else:
                    # Annual YoY: expand to prior_year → current_year
                    start_period = str(base_year - 1)
                    end_period = str(base_year)
                    period = None
                    frequency = frequency or "A"
                    logger.info(f"[orchestrate_query_plan] Growth/YoY: expanded to range {start_period}-{end_period}.")
            except (ValueError, TypeError):
                logger.warning(f"[orchestrate_query_plan] Growth intent: could not parse period '{period}' for range expansion.")

    extra_fields = {
        "consolidate_flows": consolidate_flows,
        "user_limit": original_limit,
        "period_was_defaulted": scoped_plan_extra_defaulted,
        # Flag that the default period is the current in-progress year (YTD data, not a full year)
        "is_current_year_partial": (
            scoped_plan_extra_defaulted
            and period is not None
            and str(period).isdigit()
            and int(period) == current_year
        ),
    }

    return FinalQueryPlan(
        intent=intent,
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
        limit=dal_limit,
        offset=scoped_plan.offset,
        extra=extra_fields
    )
