from typing import Any, Dict, List

def get_suggestions(facts: Dict[str, Any], query_params: Dict[str, Any]) -> List[str]:
    """Return a list of contextual follow-up query suggestions."""
    intent = facts.get("intent", "summary")
    flow = facts.get("flow", "trade")
    partner = facts.get("partner_country")
    period = facts.get("period") or "2025"

    # Clean up strings for display
    flow_str = flow or "trade"
    flow_cap = flow_str.capitalize()
    partner_name = partner if isinstance(partner, str) else partner[0] if isinstance(partner, list) and partner else None
    partner_suffix = f" with {partner_name}" if partner_name else ""

    suggestions = []

    # NEW: if the query was grouped by a dimension (e.g. MODE_OF_TRANSPORT),
    # prioritize follow-ups that drill into the specific top groups rather
    # than generic intent-based suggestions, since the user is clearly
    # interested in a per-group comparison.
    breakdown_records = facts.get("mode_breakdown_records") or facts.get("group_breakdown_records")
    if breakdown_records:
        grouped_by = facts.get("grouped_by", "group")
        top_labels = [
            r['label'].capitalize() if isinstance(r['label'], str) else r['label']
            for r in breakdown_records[:2]
        ]
        if len(top_labels) >= 2:
            suggestions.append(
                f"Show the monthly trend comparing {top_labels[0]} vs {top_labels[1]} {flow_str}s{partner_suffix}"
            )
        suggestions.append(f"What were the top products moved by {grouped_by} in {period}?")
        if partner_name:
            suggestions.append(f"Compare {grouped_by} breakdown{partner_suffix} against another partner country")
        else:
            suggestions.append(f"Show the {grouped_by} breakdown by partner country for {period}")

    elif intent == "summary":
        if partner_name:
            suggestions.append(f"Show the trend of {flow_str}s{partner_suffix} over the years")
            suggestions.append(f"What were the top products in {flow_str}s{partner_suffix} for {period}?")
            suggestions.append(f"Compare {flow_str}s{partner_suffix} against another partner country")
        else:
            suggestions.append(f"Show the breakdown of {flow_str}s by partner country for {period}")
            suggestions.append(f"What were the top partners by {flow_str} value in {period}?")
            suggestions.append(f"Show the trend of total {flow_str}s over the years")

    elif intent == "ranking":
        metric_label = "products" if facts.get("hs_code") or facts.get("hs_chapter") else "partners"
        suggestions.append(f"Show the monthly trade trend for the top {metric_label}")
        suggestions.append(f"What was the total {flow_str} value for {period}?")
        if partner_name:
            suggestions.append(f"Compare imports and exports{partner_suffix} for {period}")

    elif intent == "trend":
        suggestions.append(f"Show the breakdown of {flow_str}s by product category for {period}")
        if partner_name:
            suggestions.append(f"Compare this trend{partner_suffix} against imports from China")
        else:
            suggestions.append(f"What were the top partners by {flow_str} value in {period}?")

    elif intent == "comparison":
        countries_list = query_params.get("partner_countries") or []
        first_country = countries_list[0] if countries_list else partner_name or "China"
        suggestions.append(f"Show the monthly trend of trade with {first_country}")
        suggestions.append(f"What is the trade balance with {first_country} for {period}?")
        suggestions.append(f"Show the breakdown of trade by product for {first_country}")

    elif intent == "breakdown":
        group_by = query_params.get("group_by") or []
        is_transport = any("transport" in str(g).lower() for g in group_by)
        if is_transport:
            suggestions.append(f"Show the trend of total {flow_str}s by transport mode over the years")
        else:
            suggestions.append(f"Show the trend of total {flow_str}s for the largest product sector")
        suggestions.append(f"What were the top partners by {flow_str} value in {period}?")

    elif intent == "growth":
        suggestions.append(f"Show the trend of total {flow_str}s for {period}")
        if partner_name:
            suggestions.append(f"What is the trade balance with {partner_name} for {period}?")
        else:
            suggestions.append(f"What were the top partners by {flow_str} value in {period}?")

    elif intent == "trade_balance":
        if partner_name:
            suggestions.append(f"What is the trend of the trade balance with {partner_name} over the years?")
            suggestions.append(f"Show the breakdown of imports vs exports with {partner_name} by product category")
            suggestions.append(f"Compare the trade balance of {partner_name} against Vietnam")
        else:
            suggestions.append("What is the total trade balance of Cambodia over the years?")
            suggestions.append("Show the monthly trend of total exports and imports")

    # Absolute fallback to fill suggestions to 3
    while len(suggestions) < 3:
        fallback_queries = [
            f"What was Cambodia's total export value in {period}?",
            f"Show the monthly trade trend for {period}",
            f"What was the trade balance with China in {period}?",
        ]
        for fq in fallback_queries:
            if fq not in suggestions:
                suggestions.append(fq)
                break

    return suggestions[:3]