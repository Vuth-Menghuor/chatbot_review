"""GDCE Trade Query Service — Core Enrichment and Orchestration Pipeline Facade."""

from __future__ import annotations

from typing import Any, List, Optional

from app.core.enrichment_orchestrate import (
    apply_cambodia_perspective,
    build_groupings,
    orchestrate_query_plan,
)
from app.core.enrichment_semantic import (
    enrich_query_plan,
    resolve_country,
    resolve_dimension_value,
    resolve_dimension_value_single,
    resolve_dimensions,
    resolve_entities,
)

# Re-expose for import compatibility
__all__ = [
    "resolve_dimension_value",
    "resolve_dimension_value_single",
    "resolve_country",
    "resolve_dimensions",
    "resolve_entities",
    "enrich_query_plan",
    "apply_cambodia_perspective",
    "build_groupings",
    "orchestrate_query_plan",
    "convert_legacy_params",
    "deduce_year",
]


def convert_legacy_params(raw_params: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible helper mapping input dict params through Stage 2 -> 3 -> 4 pipeline.

    Returns the formatted FinalQueryPlan as a flat dictionary.
    """
    from app.handlers.scopes import apply_intent_scoping
    from app.schemas.query_plan import RawQueryPlan

    raw_plan = RawQueryPlan(
        intent=raw_params.get("intent", "summary"),
        raw_origin_country=raw_params.get("origin_country"),
        raw_destination_country=raw_params.get("destination_country"),
        raw_partner_countries=raw_params.get("partner_countries"),
        raw_trade_direction=raw_params.get("trade_direction"),
        raw_product=raw_params.get("hs_code") or raw_params.get("hs_chapter") or raw_params.get("product"),
        raw_sitc_section=raw_params.get("sitc_section"),
        raw_sitc_division=raw_params.get("sitc_division"),
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
        "limit": scoped.limit or final.limit,
        "offset": final.offset,
        "origin_country": scoped.origin_country,
        "destination_country": scoped.destination_country,
        "sort_order": scoped.sort_order,
        "sort_metric": scoped.sort_metric,
        "year": deduce_year(scoped.year, final.period, final.start_period, final.end_period),
        "years": scoped.years,
        "month": scoped.month,
        "quarter": scoped.quarter,
        "semester": scoped.semester,
    }

    # Flatten fields for compatibility with legacy test assertions
    res["trade_direction"] = final.filters.get("FLOW")
    partners = final.filters.get("PARTNER_COUNTRY")
    res["partner_countries"] = partners if isinstance(partners, list) else None
    res["partner_country"] = partners if isinstance(partners, str) else None
    res["mode_of_transport"] = _map_mot_to_names(final.filters.get("MODE_OF_TRANSPORT"))
    res["hs_code"] = final.filters.get("HS_HEADING") or final.filters.get("HS_CODE")
    res["hs_chapter"] = final.filters.get("HS_CHAPTER")
    res["sitc_section"] = final.filters.get("SITC_SECTION")
    res["sitc_division"] = final.filters.get("SITC_DIVISION")
    return res


def _map_mot_to_names(mot: Any) -> Optional[List[str]]:
    if not mot:
        return None
    from app.registry.semantic_registry import SEMANTIC_REGISTRY
    mot_entry = SEMANTIC_REGISTRY.get("MODE_OF_TRANSPORT")
    if not mot_entry:
        return [str(mot)] if not isinstance(mot, list) else [str(m) for m in mot]

    def get_canonical(val: str) -> str:
        val_str = str(val).strip()
        if val_str in ["air", "sea", "road", "rail", "postal", "multimodal", "fixed", "inland"]:
            return val_str
        syns = mot_entry.values_map.get(val_str)
        return syns[0] if syns else val_str

    if isinstance(mot, list):
        return [get_canonical(m) for m in mot if m]
    return [get_canonical(mot)]


def deduce_year(year: int | None, period: str | None, start_period: str | None, end_period: str | None) -> int | None:
    if year is not None:
        return year
    if period and len(period) >= 4 and period[:4].isdigit():
        return int(period[:4])
    s_year = int(start_period[:4]) if start_period and len(start_period) >= 4 and start_period[:4].isdigit() else None
    e_year = int(end_period[:4]) if end_period and len(end_period) >= 4 and end_period[:4].isdigit() else None
    if s_year and e_year:
        if s_year == e_year:
            return s_year
    elif s_year:
        return s_year
    elif e_year:
        return e_year
    return None
