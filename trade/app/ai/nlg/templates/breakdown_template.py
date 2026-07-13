"""NLG fallback template for breakdown intent."""

from typing import Any, Dict

from app.ai.nlg.format_utils import format_metric, generate_capped_list_message


def render_breakdown(
    facts: Dict[str, Any],
    flow_phrase: str,
    prod_phrase: str,
    trans_phrase: str,
    time_phrase: str,
    flow: str,
    metrics: list,
) -> str:
    """Render breakdown fallback text."""
    breakdown_records = facts.get("group_breakdown_records") or facts.get("mode_breakdown_records") or []
    grouped_by = facts.get("grouped_by", "group")

    if breakdown_records:
        total_val = sum(r["trade_value_usd"] for r in breakdown_records)

        summary_details = generate_capped_list_message(breakdown_records, label_col="label", value_col="trade_value_usd", top_n_to_name=5, metrics=metrics)

        limit = facts.get("limit") or len(breakdown_records)
        total_count = len(breakdown_records)
        subset_val = facts.get("subset_total_value") or total_val
        val_formatted = format_metric(subset_val, metrics)

        if limit < total_count:
            subset_phrase = f"showing the top {limit} of {total_count} categories (totaling {val_formatted}), "
        else:
            subset_phrase = f"across all {total_count} categories (totaling {val_formatted}), "

        header = f"Cambodia's {flow_phrase}{prod_phrase}{time_phrase} broken down by {grouped_by} was {subset_phrase}{summary_details}."

        concentration_insight = ""
        if total_val > 0 and len(breakdown_records) >= 3:
            top_3_val = sum(r["trade_value_usd"] for r in breakdown_records[:3])
            top_3_share = (top_3_val / total_val) * 100
            if top_3_share >= 50.0:
                concentration_insight = f" The top 3 categories accounted for {top_3_share:.1f}% of the total {flow or 'trade'} value."

        bullets = []
        show_limit = min(limit, 5)
        for r in breakdown_records[:show_limit]:
            lbl = r["label"].capitalize() if isinstance(r["label"], str) else str(r["label"])
            val = r["trade_value_usd"]
            share = (val / total_val * 100) if total_val > 0 else 0.0
            bullets.append(f"* {lbl}: {format_metric(val, metrics)} ({share:.1f}%)")

        if len(breakdown_records) > show_limit:
            other_val = sum(r["trade_value_usd"] for r in breakdown_records[show_limit:])
            other_share = (other_val / total_val * 100) if total_val > 0 else 0.0
            bullets.append(f"* Others: {format_metric(other_val, metrics)} ({other_share:.1f}%)")

        return f"{header}{concentration_insight}\n\n" + "\n".join(bullets)

    val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
    return f"Breakdown of {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} totaled {format_metric(val_usd, metrics)}."
