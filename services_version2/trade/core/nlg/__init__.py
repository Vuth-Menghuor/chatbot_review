from typing import Any, Dict
from core.nlg.formatters import extract_facts
from core.nlg.generator import generate_message
from core.nlg.suggestions import get_suggestions

def generate_nlg_response(payload: Dict[str, Any], query_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for Stage 6 (Natural Language Generation).

    Extracts raw facts from the payload, generates a copywriter summary,
    and appends next-step suggestions.

    Updates and returns the payload dictionary with:
    - payload["facts"]
    - payload["message"]
    - payload["suggestions"]
    """
    # 1. Extract raw facts from payload and query parameters
    facts = extract_facts(payload, query_params)
    facts["question"] = payload.get("question") or query_params.get("question") or ""

    # Inject group_by and sort so ranking generator can correctly label entity types
    group_by = query_params.get("group_by") or query_params.get("dimensions") or []
    facts["group_by"] = group_by if isinstance(group_by, list) else [group_by]
    facts["sort_param"] = query_params.get("sort") or ""

    # Intent-specific facts adjustments for trade balance
    intent = query_params.get("intent", "summary")
    if intent == "trade_balance":
        records = payload.get("records") or []
        exports_total = sum(
            float(r.get("VALUE_USD", r.get("value_usd", r.get("trade_value", 0.0))) or 0.0)
            for r in records
            if str(r.get("FLOW", r.get("flow", ""))).upper() == "EX"
        )
        imports_total = sum(
            float(r.get("VALUE_USD", r.get("value_usd", r.get("trade_value", 0.0))) or 0.0)
            for r in records
            if str(r.get("FLOW", r.get("flow", ""))).upper() == "IM"
        )
        facts["total_exports_usd"] = exports_total
        facts["total_imports_usd"] = imports_total
        facts["total_trade_value_usd"] = abs(exports_total - imports_total)  # net balance

    # Expose trade_balance and flows count for summary intent balance exposure
    summary_data = payload.get("summary") or {}
    if "trade_balance" in summary_data:
        facts["trade_balance"] = summary_data["trade_balance"]
    
    if "subset_total_value" in summary_data:
        facts["subset_total_value"] = summary_data["subset_total_value"]
    if "subset_count" in summary_data:
        facts["subset_count"] = summary_data["subset_count"]
    if "subset_label" in summary_data:
        facts["subset_label"] = summary_data["subset_label"]
    if "subset_total_weight" in summary_data:
        facts["subset_total_weight"] = summary_data["subset_total_weight"]
    if "data_quality" in summary_data:
        facts["data_quality"] = summary_data["data_quality"]
    if "execution_mode" in summary_data:
        facts["execution_mode"] = summary_data["execution_mode"]
    if "growth_downgrade_reason" in summary_data:
        facts["growth_downgrade_reason"] = summary_data["growth_downgrade_reason"]
    if query_params.get("extra", {}).get("consolidate_flows"):
        facts["consolidate_flows"] = True

    # Expose extra parameters (like volume_requested and directional_context) to facts
    extra_params = query_params.get("extra") or {}
    for k, v in extra_params.items():
        if k not in facts:
            facts[k] = v

    records = payload.get("records") or []
    ex_count = sum(1 for r in records if str(r.get("FLOW", r.get("flow", ""))).upper() == "EX")
    im_count = sum(1 for r in records if str(r.get("FLOW", r.get("flow", ""))).upper() == "IM")
    if ex_count > 0 and im_count > 0:
        facts["has_both_flows"] = True

    # Check for intra-year repeating-period patterns
    from config import get_settings
    from core.constants import NLG_REPEATING_KEYWORDS, NLG_RANGE_KEYWORDS
    settings = get_settings()

    question_lower = (facts.get("question") or "").lower()
    freq = query_params.get("frequency")
    if freq in ("M", "Q", "S") and any(kw in question_lower for kw in NLG_REPEATING_KEYWORDS):
        facts["repeating_period_pattern_requested"] = True

    # Check for data boundary transparency
    start_p = query_params.get("start_period")
    end_p = query_params.get("end_period")
    has_large_range_keyword = any(kw in question_lower for kw in NLG_RANGE_KEYWORDS)
    boundary_exceeded = False
    if start_p:
        try:
            start_yr = int(str(start_p)[:4])
            if start_yr < settings.min_available_year:
                boundary_exceeded = True
        except (ValueError, TypeError):
            pass
    if end_p:
        try:
            end_yr = int(str(end_p)[:4])
            if end_yr > settings.max_available_year:
                boundary_exceeded = True
        except (ValueError, TypeError):
            pass
    if boundary_exceeded or has_large_range_keyword:
        facts["data_boundary_exceeded"] = True

    # 2. Call generator to draft the natural language message
    message = generate_message(facts)

    # 3. Generate follow-up suggestions
    suggestions = get_suggestions(facts, query_params)

    # 4. Attach to the payload for frontend consumption
    payload["facts"] = facts
    payload["message"] = message
    payload["suggestion"] = suggestions

    return payload