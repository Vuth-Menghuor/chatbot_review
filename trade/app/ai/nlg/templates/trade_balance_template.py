"""NLG fallback template for trade balance intent."""

from typing import Any, Dict

from app.ai.nlg.format_utils import format_usd


def render_trade_balance(
    facts: Dict[str, Any],
    flow_phrase: str,
    prod_phrase: str,
    trans_phrase: str,
    period: str,
    partner: Any,
    flow: str,
) -> str:
    """Render trade balance fallback text."""
    tb_records = facts.get("trade_balance_records") or []

    if tb_records:
        period_data = {}
        for r in tb_records:
            p = r["period"]
            entry = period_data.setdefault(p, {"EX": 0.0, "IM": 0.0})
            flow_type = "EX" if str(r["flow"]).upper() == "EX" else "IM"
            entry[flow_type] += r["value_usd"]

        sorted_periods = sorted(list(period_data.keys()))
        if len(sorted_periods) >= 2:
            start_p = sorted_periods[0]
            end_p = sorted_periods[-1]

            s_data = period_data[start_p]
            e_data = period_data[end_p]

            s_bal = s_data["EX"] - s_data["IM"]
            e_bal = e_data["EX"] - e_data["IM"]

            s_status = "surplus" if s_bal >= 0 else "deficit"
            e_status = "surplus" if e_bal >= 0 else "deficit"

            partner_suffix = f" with {partner}" if partner else ""
            header = f"From {start_p} to {end_p}, Cambodia's trade balance{partner_suffix} moved from a {s_status} of {format_usd(abs(s_bal))} to a {e_status} of {format_usd(abs(e_bal))}:"

            bullets = []
            show_periods = sorted_periods
            if len(sorted_periods) > 5:
                show_periods = [sorted_periods[0], sorted_periods[len(sorted_periods)//2], sorted_periods[-1]]

            for p in show_periods:
                p_ex = period_data[p]["EX"]
                p_im = period_data[p]["IM"]
                p_bal = p_ex - p_im
                p_status = "Surplus" if p_bal >= 0 else "Deficit"
                bullets.append(f"* {p}: {format_usd(abs(p_bal))} ({p_status}) [Exports: {format_usd(p_ex)}, Imports: {format_usd(p_im)}]")

            return f"{header}\n\n" + "\n".join(bullets)

    exports = facts.get("total_exports_usd") or 0.0
    imports = facts.get("total_imports_usd") or 0.0

    if exports == 0.0 and imports == 0.0:
        if flow == "export":
            exports = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        elif flow == "import":
            imports = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0

    balance = exports - imports
    bal_str = format_usd(abs(balance))
    status = "surplus" if balance >= 0 else "deficit"

    partner_phrase = f" with {partner}" if partner else ""
    header = f"In {period}, Cambodia recorded a trade {status} of {bal_str}{partner_phrase}, driven by {format_usd(exports)} in exports against {format_usd(imports)} in imports."

    bullets = [
        f"* Exports: {format_usd(exports)}",
        f"* Imports: {format_usd(imports)}",
        f"* Trade {status.capitalize()}: {bal_str}"
    ]
    return f"{header}\n\n" + "\n".join(bullets)
