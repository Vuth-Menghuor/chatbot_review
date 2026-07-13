"""NLG fallback template for ranking intent."""

from typing import Any, Dict

from app.ai.nlg.format_utils import format_metric, generate_ranking_message


def render_ranking(
    facts: Dict[str, Any],
    period: str,
    metrics: list,
) -> str:
    """Render ranking fallback text."""
    records = facts.get("ranking_records") or []
    sort_order = facts.get("sort_order", "desc")
    limit = facts.get("limit") or len(records)

    # Determine the entity type being ranked (partner, transport, product, etc.)
    # Prefer the actual ranked dimension detected from records; fall back to group_by.
    ranked_dim = (facts.get("ranked_dimension") or "").upper()
    group_by_dims = [str(g).upper() for g in (facts.get("group_by") or [])]
    if ranked_dim == "MODE_OF_TRANSPORT" or "MODE_OF_TRANSPORT" in group_by_dims:
        entity_label = "transport mode"
        entity_label_plural = "transport modes"
    elif ranked_dim == "HS_HEADING" or "HS_HEADING" in group_by_dims:
        entity_label = "product"
        entity_label_plural = "products"
    elif ranked_dim == "HS_CHAPTER" or "HS_CHAPTER" in group_by_dims:
        entity_label = "HS chapter"
        entity_label_plural = "HS chapters"
    elif ranked_dim == "SITC_SECTION" or "SITC_SECTION" in group_by_dims:
        entity_label = "SITC section"
        entity_label_plural = "SITC sections"
    elif ranked_dim == "SITC_DIVISION" or "SITC_DIVISION" in group_by_dims:
        entity_label = "SITC division"
        entity_label_plural = "SITC divisions"
    else:
        entity_label = "partner"
        entity_label_plural = "partners"

    # Determine if sorted by weight
    sort_param = str(facts.get("sort_param") or "")
    sorted_by_weight = "NET_WEIGHT" in sort_param.upper() or "WEIGHT" in sort_param.upper()

    # Ambiguous trade flow disclosure (Section 18)
    flow_filter = facts.get("flow")
    consolidate_flows = facts.get("consolidate_flows", False)
    if not flow_filter:
        scope_phrase = "combined import and export trade" if consolidate_flows else "trade"
    else:
        scope_phrase = "export" if flow_filter == "export" else "import"

    # Add weight-sort clarification when applicable
    sort_basis_note = " (ranked by trade volume / weight)" if sorted_by_weight else ""

    # Value column selection: show weight values when sorted by weight
    value_col = "weight_kg" if sorted_by_weight else "trade_value_usd"

    # Special case: single-result response (e.g. "highest X" with only 1 item)
    if len(records) == 1:
        r = records[0]
        lbl = r.get("label") or "Unknown"
        val = r.get(value_col, 0.0)
        val_str = format_metric(val, metrics, value_col=value_col)
        direction_word = "highest" if str(sort_order).lower() != "asc" else "lowest"
        return (
            f"In {period}, {lbl} recorded the {direction_word} {scope_phrase} value among {entity_label_plural} "
            f"at {val_str}{sort_basis_note}."
        ) if period and period != "the selected period" else (
            f"{lbl} recorded the {direction_word} {scope_phrase} value among {entity_label_plural} "
            f"at {val_str}{sort_basis_note}."
        )

    message_prefix = f"Based on {scope_phrase} values{sort_basis_note}, "

    # Ranking total value labeling adjustment (Section 16)
    subset_val = facts.get("subset_total_value") or sum(float(r.get(value_col, 0.0)) for r in records)
    subset_label = facts.get("subset_label") or (f"top {limit}" if str(sort_order).lower() != "asc" else f"bottom {limit}")

    val_formatted = format_metric(subset_val, metrics, value_col=value_col)
    subset_phrase = f"among Cambodia's {scope_phrase} {entity_label_plural}, the {subset_label} shown here total {val_formatted}, "

    # Truncation-capped summary phrase (Section 14)
    summary_details = generate_ranking_message(records, label_col="label", value_col=value_col, top_n_to_name=5, metrics=facts.get("metrics"))
    summary_sentence = f"{message_prefix}{subset_phrase}{summary_details}."

    # Build the detailed list items below
    list_items = []
    for i, r in enumerate(records[:limit]):
        lbl = r.get("label") or "Unknown"
        val = r.get(value_col, 0.0)
        val_str = format_metric(val, metrics, value_col=value_col)
        list_items.append(f"{i+1}. {lbl} ({val_str})")

    if not list_items:
        return f"No ranking records found for {period}."

    return f"{summary_sentence}\n\n" + "\n".join(list_items)
