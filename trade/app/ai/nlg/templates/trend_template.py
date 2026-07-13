"""NLG fallback template for trend intent."""

from typing import Any, Dict

from app.ai.nlg.format_utils import format_metric


def render_trend(
    facts: Dict[str, Any],
    flow_phrase: str,
    prod_phrase: str,
    trans_phrase: str,
    period: str,
    partner: Any,
    metrics: list,
) -> str:
    """Render trend fallback text."""
    records = facts.get("trend_records") or []
    if not records:
        val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {period} was {format_metric(val_usd, metrics)}."

    # Check if we have multiple flows for identical periods
    distinct_periods = sorted(list(set(str(r.get("period")) for r in records if r.get("period") is not None)))
    has_same_period_diff_flow = len(distinct_periods) < len(records)

    if has_same_period_diff_flow:
        # Group EX and IM flows by period
        grouped_periods = {}
        for r in records:
            p = r["period"]
            flow_val = str(r.get("flow", "")).upper()
            val = r["trade_value_usd"]
            grouped_periods.setdefault(p, {})[flow_val] = val

        partner_phrase = f" with {partner}" if partner else ""
        if len(distinct_periods) == 1:
            p = distinct_periods[0]
            p_ex = grouped_periods[p].get("EX", 0.0)
            p_im = grouped_periods[p].get("IM", 0.0)
            return f"Cambodia's trade{partner_phrase} in {p} showed exports of {format_metric(p_ex, metrics)} and imports of {format_metric(p_im, metrics)}."

        start_p = distinct_periods[0]
        end_p = distinct_periods[-1]
        header = f"Cambodia's trade{partner_phrase} from {start_p} to {end_p} showed distinct export and import flows:"
        bullets = []
        for p in distinct_periods:
            p_ex = grouped_periods[p].get("EX", 0.0)
            p_im = grouped_periods[p].get("IM", 0.0)
            bullets.append(f"* {p}: Exports {format_metric(p_ex, metrics)}, Imports {format_metric(p_im, metrics)}")
        return f"{header}\n\n" + "\n".join(bullets)

    start_rec = records[0]
    end_rec = records[-1]

    start_p = start_rec["period"]
    end_p = end_rec["period"]

    start_val = start_rec["trade_value_usd"]
    end_val = end_rec["trade_value_usd"]

    if end_val > start_val * 1.05:
        movement = "showed an upward trend, growing"
    elif end_val < start_val * 0.95:
        movement = "showed a downward trend, declining"
    else:
        movement = "remained stable,"

    header = f"From {start_p} to {end_p}, Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} {movement} from {format_metric(start_val, metrics)} to {format_metric(end_val, metrics)}:"

    bullets = []
    show_records = records
    if len(records) > 5:
        show_records = [records[0], records[len(records)//2], records[-1]]

    for r in show_records:
        p_label = r["period"]
        p_val = r["trade_value_usd"]
        bullets.append(f"* {p_label}: {format_metric(p_val, metrics)}")

    return f"{header}\n\n" + "\n".join(bullets)
