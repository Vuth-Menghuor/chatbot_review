"""Trade Query Scopes — data and visualization scope definitions.

Derives the dimensions and measures dynamically from core/semantic_registry.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.registry.semantic_registry import INTENT_RULES, STRUCTURE
from app.schemas.query_plan import EnrichedQueryPlan, ScopedQueryPlan

# Query Intents
QUERY_INTENTS: list[str] = list(INTENT_RULES.keys())

# # Dimensions derived from structure registry
# PROVEN_DIMENSIONS: list[str] = [
#     code for code, f in STRUCTURE_REGISTRY.items()
#     if f.field_type == "dimension" and f.system != "SITC"
# ]

# ASPIRATIONAL_DIMENSIONS: list[str] = [
#     code for code, f in STRUCTURE_REGISTRY.items()
#     if f.field_type == "dimension" and f.system == "SITC"
# ] + ["PERIOD", "COUNTRY"]

DIMENSIONS: list[str] = list(STRUCTURE["dimensions"].keys()) + ["PERIOD", "COUNTRY"]

# Measures derived from structure registry
PROVEN_MEASURES: list[str] = ["VALUE_USD", "NET_WEIGHT"]

# ASPIRATIONAL_MEASURES: list[str] = [
#     code for code in STRUCTURE["measures"].keys()
#     if code not in PROVEN_MEASURES
# ] + ["GROWTH_RATE", "MARKET_SHARE"]

MEASURES: list[str] = list(STRUCTURE["measures"].keys()) + ["GROWTH_RATE", "MARKET_SHARE"]

CAPABILITIES: list[str] = [
    "filtering",
    "grouping",
    "aggregation",
    "sorting",
    "pagination",
    "period_selection",
]

# Visualization types
VISUALIZATION_TYPES: list[str] = [
    "table",
    "bar_chart",
    "line_chart",
    "pie_chart",
]

# Visualizations that make sense for each intent
INTENT_VISUALIZATIONS: dict[str, list[str]] = {
    "summary":    ["table", "pie_chart"],
    "ranking":    ["bar_chart", "table"],
    "trend":      ["line_chart", "table"],
    "comparison": ["bar_chart", "table"],
    "breakdown":  ["pie_chart", "table"],
    "growth":     ["bar_chart", "line_chart", "table"],
    "trade_balance": ["bar_chart", "table"],
}

# Default measures per intent
INTENT_MEASURES: dict[str, list[str]] = {
    "summary":    ["VALUE_USD", "NET_WEIGHT"],
    "ranking":    ["VALUE_USD", "NET_WEIGHT"],
    "trend":      ["VALUE_USD", "NET_WEIGHT"],
    "comparison": ["VALUE_USD", "NET_WEIGHT"],
    "breakdown":  ["VALUE_USD", "NET_WEIGHT"],
    "growth":     ["VALUE_USD", "NET_WEIGHT"],
    "trade_balance": ["VALUE_USD", "NET_WEIGHT"],
}


@dataclass
class ScopeConfig:
    """Full scope configuration for a single intent."""

    intent: str
    dimensions: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    visualizations: list[str] = field(default_factory=list)


def get_scope_config(intent: str) -> ScopeConfig:
    """Return the full data + visualization scope for an intent."""
    return ScopeConfig(
        intent=intent,
        dimensions=DIMENSIONS,
        measures=INTENT_MEASURES.get(intent, PROVEN_MEASURES),
        capabilities=CAPABILITIES,
        visualizations=INTENT_VISUALIZATIONS.get(intent, ["table"]),
    )


def apply_intent_scoping(enriched_plan: EnrichedQueryPlan) -> ScopedQueryPlan:
    """Stage 3: Intent Scoping and Scoped Query Plan generation.

    Resolves HS vs SITC selection, applies base country defaults, handles Cambodia-centric trade flips,
    and returns a ScopedQueryPlan containing finalized scoping constraints.
    """
    intent = enriched_plan.intent
    version = enriched_plan.version

    # 1. HS vs SITC Enforcement (Stage 3)
    # If grouping or filters refer to SITC, enforce SITC.
    # If specific HS code/chapter or generic product is matched, enforce HS.
    # Otherwise fallback to the Stage 2 suggestion.
    has_sitc_filter = enriched_plan.sitc_section or enriched_plan.sitc_division
    has_sitc_group = False
    if enriched_plan.group_by:
        has_sitc_group = any("SITC" in str(g).upper() for g in enriched_plan.group_by)

    has_hs_filter = enriched_plan.hs_code or enriched_plan.hs_chapter
    has_hs_group = False
    if enriched_plan.group_by:
        has_hs_group = any("HS" in str(g).upper() for g in enriched_plan.group_by)

    classification_system = enriched_plan.hs_vs_sitc_suggestion or "HS"
    if has_hs_group and not has_sitc_group:
        classification_system = "HS"
    elif has_sitc_group and not has_hs_group:
        classification_system = "SITC"
    elif has_hs_filter and not has_sitc_filter:
        classification_system = "HS"
    elif has_sitc_filter and not has_hs_filter:
        classification_system = "SITC"
    elif enriched_plan.hs_vs_sitc_suggestion:
        classification_system = enriched_plan.hs_vs_sitc_suggestion
    elif has_hs_filter or has_hs_group:
        classification_system = "HS"
    elif has_sitc_filter or has_sitc_group:
        classification_system = "SITC"


    # Enforce classification constraints on the plan fields
    hs_code = enriched_plan.hs_code
    hs_chapter = enriched_plan.hs_chapter
    sitc_section = enriched_plan.sitc_section
    sitc_division = enriched_plan.sitc_division

    if classification_system == "HS":
        sitc_section = None
        sitc_division = None
    else:  # SITC
        hs_code = None
        hs_chapter = None

    # 2. Base country defaulting and flipping (Stage 3 logic)
    origin = enriched_plan.origin_country
    dest = enriched_plan.destination_country
    direction = enriched_plan.trade_direction
    partner_countries = enriched_plan.partner_countries

    # Default trade balance intent base country
    if intent == "trade_balance":
        if origin and not dest:
            dest = origin
            origin = "KH"
        elif dest and not origin:
            origin = "KH"
        elif not origin and not dest:
            origin = "KH"
        # Clear flow filter to query both EX/IM directions
        direction = None

    # Direction normalization and flipping logic (Cambodia-centric)
    if direction:
        # Check single-country base flip
        if direction == "IM" and origin == "KH" and not dest:
            origin = None
            dest = "KH"
        elif direction == "EX" and dest == "KH" and not origin:
            dest = None
            origin = "KH"

        # Direction flip rules based on origin/destination context
        if intent != "comparison":
            should_flip = False
            if direction == "EX":
                if (origin and origin.upper() != "KH") or (dest and dest.upper() == "KH"):
                    should_flip = True
            elif direction == "IM":
                if (dest and dest.upper() != "KH") or (origin and origin.upper() == "KH"):
                    should_flip = True

            if should_flip:
                direction = "IM" if direction == "EX" else "EX"

            # Fill in implicit Cambodia (KH)
            if direction == "EX":
                if not origin:
                    origin = "KH"
                if not dest and origin != "KH":
                    dest = origin
                    origin = "KH"
            elif direction == "IM":
                if not dest:
                    dest = "KH"
                if not origin and dest != "KH":
                    origin = dest
                    dest = "KH"

    # For comparison intent: both countries become partner_countries list, and we filter out KH
    if intent == "comparison":
        if partner_countries is not None:
            filtered = []
            for c in partner_countries:
                if str(c).upper().strip() != "KH" and str(c).strip().lower() != "cambodia":
                    filtered.append(c)
            partner_countries = filtered if filtered else None
        else:
            countries_deduced = []
            if origin and str(origin).upper().strip() != "KH":
                countries_deduced.append(origin)
            if dest and str(dest).upper().strip() != "KH":
                if dest not in countries_deduced:
                    countries_deduced.append(dest)
            partner_countries = countries_deduced if countries_deduced else None

        # Align origin_country and destination_country to reflect the Cambodia-centric flow
        if direction == "EX":
            origin = "KH"
            dest = None
        elif direction == "IM":
            origin = None
            dest = "KH"
        else:
            origin = None
            dest = None

    # 3. Resolve Metrics & Group By Constraints
    from app.registry.strategies import STRATEGIES
    strategy = STRATEGIES.get(intent)

    metrics = enriched_plan.metrics
    if not metrics:
        metrics = strategy.default_metrics if strategy else ["VALUE_USD", "NET_WEIGHT"]

    group_by = enriched_plan.group_by
    dimensions = enriched_plan.dimensions

    # Fallback group_by and dimensions matching intent allowed lists
    raw_dims = [str(d) for d in dimensions] if isinstance(dimensions, list) else []
    raw_group = [str(g) for g in group_by] if isinstance(group_by, list) else []

    if not raw_dims and not raw_group:
        if intent == "breakdown":
            question_lower = (enriched_plan.question or "").lower()
            if any(term in question_lower for term in ["transport", "mot", "mode", "ship", "plane", "truck", "train", "post", "carrier", "way"]):
                raw_dims = ["MODE_OF_TRANSPORT"]
                raw_group = ["MODE_OF_TRANSPORT"]
            elif classification_system == "SITC" or any(term in question_lower for term in ["sector", "industry", "sitc", "division"]):
                raw_dims = ["SITC_DIVISION"]
                raw_group = ["SITC_DIVISION"]
            else:
                raw_dims = ["HS_CHAPTER"]
                raw_group = ["HS_CHAPTER"]
        elif intent == "ranking":
            question_lower = (enriched_plan.question or "").lower()
            if any(term in question_lower for term in ["transport", "mot", "mode", "ship", "plane", "flight", "air", "sea", "road", "rail"]):
                raw_dims = ["MODE_OF_TRANSPORT"]
                raw_group = ["MODE_OF_TRANSPORT"]
            elif any(term in question_lower for term in ["product", "products", "commodity", "commodities"]):
                if classification_system == "SITC" or any(term in question_lower for term in ["sector", "industry", "sitc"]):
                    raw_dims = ["SITC_DIVISION"]
                    raw_group = ["SITC_DIVISION"]
                else:
                    raw_dims = ["HS_CHAPTER"]
                    raw_group = ["HS_CHAPTER"]
            elif strategy:
                raw_dims = strategy.default_dimensions
                raw_group = strategy.default_group_by
        elif strategy:
            raw_dims = strategy.default_dimensions
            raw_group = strategy.default_group_by
        else:
            inferred = ["FLOW", "PARTNER_COUNTRY"] if intent in ("trend", "summary", "trade_balance") else ["PARTNER_COUNTRY"]
            raw_dims = inferred
            raw_group = inferred
    elif not raw_dims:
        raw_dims = raw_group
    elif not raw_group:
        raw_group = raw_dims

    if intent == "trade_balance":
        if "FLOW" not in raw_group:
            raw_group.append("FLOW")
        if "FLOW" not in raw_dims:
            raw_dims.append("FLOW")

    # Filter/Adjust according to Classification System choices
    final_group = []
    for g in raw_group:
        if classification_system == "HS" and "SITC" in g:
            if g == "SITC_SECTION": final_group.append("HS_CHAPTER")
            elif g == "SITC_DIVISION": final_group.append("HS_HEADING")
        elif classification_system == "SITC" and "HS" in g:
            if g == "HS_CHAPTER": final_group.append("SITC_SECTION")
            elif g == "HS_HEADING": final_group.append("SITC_DIVISION")
        else:
            final_group.append(g)

    final_dims = []
    for d in raw_dims:
        if classification_system == "HS" and "SITC" in d:
            if d == "SITC_SECTION": final_dims.append("HS_CHAPTER")
            elif d == "SITC_DIVISION": final_dims.append("HS_HEADING")
        elif classification_system == "SITC" and "HS" in d:
            if d == "HS_CHAPTER": final_dims.append("SITC_SECTION")
            elif d == "HS_HEADING": final_dims.append("SITC_DIVISION")
        else:
            final_dims.append(d)

    # Ensure SITC filter dimensions are present in group_by/dimensions so the DAL
    # can route the query to the correct classification table.
    if sitc_division and "SITC_DIVISION" not in final_group:
        final_group.append("SITC_DIVISION")
    if sitc_section and "SITC_SECTION" not in final_group:
        final_group.append("SITC_SECTION")
    if sitc_division and "SITC_DIVISION" not in final_dims:
        final_dims.append("SITC_DIVISION")
    if sitc_section and "SITC_SECTION" not in final_dims:
        final_dims.append("SITC_SECTION")

    # Sort & Limits defaults
    default_limit = strategy.default_limit if strategy else 1000
    limit = enriched_plan.limit if enriched_plan.limit is not None else default_limit
    offset = enriched_plan.offset if enriched_plan.offset is not None else 0

    return ScopedQueryPlan(
        intent=intent,
        version=version,
        origin_country=origin,
        destination_country=dest,
        partner_countries=partner_countries,
        trade_direction=direction,
        hs_code=hs_code,
        hs_chapter=hs_chapter,
        sitc_section=sitc_section,
        sitc_division=sitc_division,
        mode_of_transport=enriched_plan.mode_of_transport,
        year=enriched_plan.year,
        years=enriched_plan.years,
        month=enriched_plan.month,
        quarter=enriched_plan.quarter,
        semester=enriched_plan.semester,
        start_period=enriched_plan.start_period,
        end_period=enriched_plan.end_period,
        frequency=enriched_plan.frequency,
        group_by=final_group,
        dimensions=final_dims,
        metrics=metrics,
        sort_order=enriched_plan.sort_order,
        sort_metric=enriched_plan.sort_metric,
        limit=limit,
        offset=offset,
        chart_preference=enriched_plan.chart_preference,
        question=enriched_plan.question,
    )
