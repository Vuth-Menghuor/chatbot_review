"""NLG fallback template for summary intent."""

from typing import Any, Dict

from app.ai.nlg.format_utils import format_usd, format_weight


def render_summary(
    facts: Dict[str, Any],
    flow_phrase: str,
    prod_phrase: str,
    trans_phrase: str,
    time_phrase: str,
    ytd_suffix: str,
) -> str:
    """Render summary fallback text."""
    flow = facts.get("flow", "trade")
    metrics = facts.get("metrics") or ["VALUE_USD"]

    val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
    weight = facts.get("total_weight_kg") or facts.get("subset_weight_kg") or 0.0
    val_formatted = format_usd(val_usd)

    # Plural verb alignment
    verb = "were" if flow in ["export", "import"] else "was"

    balance_suffix = ""
    if facts.get("has_both_flows") and facts.get("trade_balance") is not None:
        tb = float(facts["trade_balance"])
        tb_type = "surplus" if tb >= 0 else "deficit"
        tb_formatted = format_usd(abs(tb))
        balance_suffix = f" (a {tb_type} of {tb_formatted})"

    if "NET_WEIGHT" in metrics or facts.get("total_weight_kg") or facts.get("subset_weight_kg"):
        weight_str = format_weight(weight)
        if "NET_WEIGHT" in metrics and "VALUE_USD" not in metrics:
            return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} {verb} {weight_str}{ytd_suffix}."
        return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} {verb} {val_formatted} (Net Weight: {weight_str}){balance_suffix}{ytd_suffix}."

    return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} {verb} {val_formatted}{balance_suffix}{ytd_suffix}."
