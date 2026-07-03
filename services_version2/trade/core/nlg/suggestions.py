from typing import Any, Dict, List

def _clean_label(label: Any) -> str:
    """Cap and clean long dimension descriptions for suggestions."""
    if not label:
        return ""
    s = str(label).strip()
    if len(s) > 25:
        # Split on commas/semicolons to get first friendly part, or truncate
        parts = [p.strip() for p in s.replace(";", ",").split(",")]
        first_part = parts[0]
        if len(first_part) > 25:
            return first_part[:22] + "..."
        return first_part
    return s


from config import get_settings

def get_suggestions(facts: Dict[str, Any], query_params: Dict[str, Any]) -> List[str]:
    """Return a list of contextual follow-up query suggestions."""
    settings = get_settings()
    default_countries = settings.default_suggestion_countries

    intent = facts.get("intent", "summary")
    flow = facts.get("flow", "trade")
    partner = facts.get("partner_country")
    period = facts.get("period") or settings.default_suggestion_period

    # Clean up strings for display
    flow_str = flow or "trade"
    flow_cap = flow_str.capitalize()
    partner_name = partner if isinstance(partner, str) else partner[0] if isinstance(partner, list) and partner else None
    partner_suffix = f" with {partner_name}" if partner_name else ""

    # Resolve target comparison country to prevent self-reference
    first_default = default_countries[0]
    second_default = default_countries[1]
    third_default = default_countries[2]

    target_country = second_default
    if partner_name:
        partner_upper = str(partner_name).strip().upper()
        first_default_upper = first_default.upper()
        if partner_upper in (first_default_upper, "CN"):
            target_country = second_default
        else:
            target_country = first_default

    # Pluralization resolution (fixes "trades" grammatical bug)
    flow_plural = "exports" if flow == "export" else "imports" if flow == "import" else "trade"

    # Resolve product context
    prod_name = None
    prod_code = facts.get("hs_code") or facts.get("hs_chapter") or facts.get("sitc_division") or facts.get("sitc_section")
    if prod_code:
        from core.product_resolver import resolve_hs_to_name
        prod_name = resolve_hs_to_name(str(prod_code))
    product_phrase = f" of {prod_name}" if prod_name else ""

    # Clean up prepositions to avoid double prepositions like "for from X to Y"
    p_lower = str(period).strip().lower()
    if p_lower.startswith("from") or p_lower.startswith("since") or p_lower.startswith("until"):
        in_period = f" {period}"
        for_period = f" {period}"
    else:
        in_period = f" in {period}"
        for_period = f" for {period}"

    suggestions = []

    # 1. Comparison intent — must be checked BEFORE breakdown_records because
    # comparison queries also group by PARTNER_COUNTRY and would otherwise
    # incorrectly trigger the breakdown template.
    # Fix #15: Multi-entity comparisons address multiple partners
    if intent == "comparison":
        countries_list = query_params.get("partner_countries") or []
        first_country = countries_list[0] if countries_list else partner_name or first_default
        second_country = countries_list[1] if len(countries_list) >= 2 else second_default
        if not countries_list and first_country == second_country:
            second_country = third_default
        suggestions.append(f"Show the monthly trend of trade with {first_country}")
        suggestions.append(f"What is the trade balance with {second_country}{for_period}?")
        suggestions.append(f"Compare breakdown of trade by product for {first_country} vs {second_country}")

    # 2. Grouped breakdown follow-up queries (priority drill-downs)
    # Fix #16: Truncate long descriptions & clean partner_suffix duplicate prepositions
    elif breakdown_records := (facts.get("mode_breakdown_records") or facts.get("group_breakdown_records")):
        grouped_by = facts.get("grouped_by", "group")
        top_labels = [
            _clean_label(r['label']).capitalize() if isinstance(r['label'], str) else _clean_label(r['label'])
            for r in breakdown_records[:2]
        ]
        
        # Avoid "comparing Vietnam vs Thailand trade with Vietnam" redundant suffix
        clean_suffix = partner_suffix
        if grouped_by in ("country", "partner_country", "PARTNER_COUNTRY"):
            clean_suffix = ""
            
        if len(top_labels) >= 2:
            suggestions.append(
                f"Show the monthly trend comparing {top_labels[0]} vs {top_labels[1]} {flow_plural}{product_phrase}{clean_suffix}"
            )
        suggestions.append(f"What were the top products moved by {grouped_by}{in_period}?")
        if partner_name:
            suggestions.append(f"Compare {grouped_by} breakdown with {partner_name} against {target_country}")
        else:
            suggestions.append(f"Show the {grouped_by} breakdown by partner country{for_period}")

    # 3. Context-aware intent follow-up queries
    elif intent == "summary":
        if partner_name and prod_name:
            suggestions.append(f"Show the trend of {prod_name} {flow_plural}{partner_suffix} over the years")
            suggestions.append(f"Compare Cambodia's {prod_name} {flow_plural} with {partner_name} against {target_country}")
            suggestions.append(f"Show the breakdown of {prod_name} {flow_plural}{partner_suffix} by transport mode")
        elif partner_name:
            suggestions.append(f"Show the trend of {flow_plural}{partner_suffix} over the years")
            suggestions.append(f"What were the top products in {flow_plural}{partner_suffix}{in_period}?")
            suggestions.append(f"Compare Cambodia's {flow_plural} with {partner_name} against {target_country}")
        elif prod_name:
            suggestions.append(f"Show the breakdown of {prod_name} {flow_plural} by partner country{for_period}")
            suggestions.append(f"What were the top partners for {prod_name} {flow_plural}{in_period}?")
            suggestions.append(f"Show the trend of {prod_name} {flow_plural} over the years")
        else:
            suggestions.append(f"Show the breakdown of {flow_plural} by partner country{for_period}")
            suggestions.append(f"What were the top partners by {flow_str} value{in_period}?")
            suggestions.append(f"Show the trend of total {flow_plural} over the years")

    elif intent == "ranking":
        metric_label = "products" if facts.get("hs_code") or facts.get("hs_chapter") or prod_name else "partners"
        suggestions.append(f"Show the monthly trade trend for the top {metric_label}")
        suggestions.append(f"What was the total {flow_str} value{for_period}?")
        if partner_name:
            suggestions.append(f"Compare imports and exports{partner_suffix}{for_period}")

    elif intent == "trend":
        suggestions.append(f"Show the breakdown of {flow_plural}{product_phrase} by product category{for_period}")
        if partner_name:
            suggestions.append(f"Compare this trend{partner_suffix} against imports from China")
        else:
            suggestions.append(f"What were the top partners by {flow_str} value{in_period}?")

    elif intent == "breakdown":
        group_by = query_params.get("group_by") or []
        is_transport = any("transport" in str(g).lower() for g in group_by)
        if is_transport:
            suggestions.append(f"Show the trend of total {flow_plural}{product_phrase} by transport mode over the years")
        else:
            suggestions.append(f"Show the trend of total {flow_plural} for the largest product sector")
        suggestions.append(f"What were the top partners by {flow_str} value{in_period}?")

    elif intent == "growth":
        suggestions.append(f"Show the trend of total {flow_plural}{product_phrase}{for_period}")
        if partner_name:
            suggestions.append(f"What is the trade balance with {partner_name}{for_period}?")
        else:
            suggestions.append(f"What were the top partners by {flow_str} value{in_period}?")

    elif intent == "trade_balance":
        if partner_name:
            suggestions.append(f"What is the trend of the trade balance with {partner_name} over the years?")
            suggestions.append(f"Show the breakdown of imports vs exports with {partner_name} by product category")
            suggestions.append(f"Compare the trade balance of {partner_name} against {target_country}")
        else:
            suggestions.append("What is the total trade balance of Cambodia over the years?")
            suggestions.append("Show the monthly trend of total exports and imports")

    # Absolute fallback to fill suggestions to 3
    while len(suggestions) < 3:
        fallback_queries = [
            f"What was Cambodia's total export value{in_period}?",
            f"Show the monthly trade trend{for_period}",
            f"What was the trade balance with {default_countries[0] if default_countries else 'China'}{in_period}?",
        ]
        for fq in fallback_queries:
            if fq not in suggestions:
                suggestions.append(fq)
                break

    # Add a standing suggestion prompting the user to confirm/narrow the year when defaulted
    if facts.get("period_was_defaulted") or facts.get("is_current_year_partial"):
        # Insert as the second suggestion so it is guaranteed to be returned within the cap of 3
        suggestions.insert(1, "Specify a year for more precise results (e.g. 'in 2025')")

    return suggestions[:3]