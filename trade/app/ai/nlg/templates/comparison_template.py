"""NLG fallback template for comparison intent."""

from collections import defaultdict
from typing import Any, Dict

from app.ai.nlg.format_utils import format_metric


def render_comparison(
    facts: Dict[str, Any],
    flow_phrase: str,
    prod_phrase: str,
    trans_phrase: str,
    time_phrase: str,
    flow: str,
    metrics: list,
    question_lower: str,
) -> str:
    """Render comparison fallback text."""
    records = facts.get("comparison_records") or []

    if len(records) >= 2:
        is_weight_comparison = any("WEIGHT" in str(m).upper() for m in metrics) and "VALUE_USD" not in [str(m).upper() for m in metrics]
        if facts.get("volume_requested") and any("WEIGHT" in str(m).upper() for m in metrics):
            is_weight_comparison = True

        val_key = "weight_kg" if is_weight_comparison else "trade_value_usd"

        # Detect time-series comparison (records have periods)
        periods = sorted(list(set(str(r.get("period")) for r in records if r.get("period") is not None)))
        is_time_series = len(periods) >= 2

        if is_time_series:
            # Group by country and compute trend statistics
            country_series = defaultdict(list)
            for r in records:
                c = r.get("country", "Unknown")
                country_series[c].append(r)

            for c in country_series:
                country_series[c].sort(key=lambda x: str(x.get("period", "")))

            # Build trend description
            trend_parts = []
            for c, series in sorted(country_series.items(), key=lambda x: sum(r.get(val_key, 0.0) for r in x[1]), reverse=True):
                vals = [r.get(val_key, 0.0) for r in series]
                min_val = min(vals)
                max_val = max(vals)
                min_idx = vals.index(min_val)
                max_idx = vals.index(max_val)
                min_period = series[min_idx].get("period", "")
                max_period = series[max_idx].get("period", "")

                # Try to describe peak/trough naturally
                peak_phrase = f"peaking at {format_metric(max_val, metrics)} in {max_period}" if max_period else f"peaking at {format_metric(max_val, metrics)}"
                trough_phrase = f"and reaching a low of {format_metric(min_val, metrics)} in {min_period}" if min_period else f"and a low of {format_metric(min_val, metrics)}"
                trend_parts.append(f"{c} ranged from {format_metric(min_val, metrics)} to {format_metric(max_val, metrics)} ({peak_phrase}, {trough_phrase})")

            # Determine which country is consistently higher
            if len(country_series) == 2:
                names = list(country_series.keys())
                total_0 = sum(r.get(val_key, 0.0) for r in country_series[names[0]])
                total_1 = sum(r.get(val_key, 0.0) for r in country_series[names[1]])
                if total_0 > total_1 * 1.05:
                    higher = names[0]
                    lower = names[1]
                elif total_1 > total_0 * 1.05:
                    higher = names[1]
                    lower = names[0]
                else:
                    higher = None
                    lower = None

                if higher:
                    verdict = f" Overall, {higher} recorded higher {flow or 'trade'} values than {lower} across the period."
                else:
                    verdict = " Both countries showed comparable overall levels."
            else:
                verdict = ""

            return f"Cambodia's {flow or 'trade'} trend{prod_phrase}{time_phrase} showed: " + "; ".join(trend_parts) + "." + verdict

        # Simple (non-time-series) comparison
        sorted_recs = sorted(records, key=lambda x: x.get(val_key, 0.0), reverse=True)
        leader = sorted_recs[0]
        runner_up = sorted_recs[1]

        lead_name = leader["country"]
        run_name = runner_up["country"]

        lead_val = leader.get(val_key, 0.0)
        run_val = runner_up.get(val_key, 0.0)

        diff = lead_val - run_val
        diff_pct = (diff / run_val * 100) if run_val > 0 else 0.0

        lead_val_str = format_metric(lead_val, metrics)
        run_val_str = format_metric(run_val, metrics)
        diff_str = format_metric(diff, metrics)

        flow_word = "Exports" if flow == "export" else "Imports" if flow == "import" else "Trade"
        prep = "to" if flow == "export" else "from" if flow == "import" else "with"

        metric_disclosure = ""
        if facts.get("volume_requested"):
            if is_weight_comparison:
                metric_disclosure = " by physical volume (KG)"
            else:
                metric_disclosure = " by trade value (USD)"

        # Detect literal ask phrasing
        asks_difference = any(kw in question_lower for kw in ["difference between", "difference in", "how much more", "gap between"])
        asks_bigger = any(kw in question_lower for kw in ["which is bigger", "which is larger", "which is greater", "who is bigger", "bigger trade partner", "larger trade partner"])

        if asks_bigger and len(records) == 2:
            return f"{lead_name} is Cambodia's larger trade partner{prod_phrase}{time_phrase} with {format_metric(lead_val, metrics)} {prep} {lead_name}, compared to {format_metric(run_val, metrics)} {prep} {run_name}."

        if asks_difference and len(records) == 2:
            return f"The difference in {flow_word.lower()}{prod_phrase} between {lead_name} and {run_name}{time_phrase} is {diff_str}: {format_metric(lead_val, metrics)} for {lead_name} versus {format_metric(run_val, metrics)} for {run_name}."

        header = f"{flow_word}{prod_phrase} {prep} {lead_name}{metric_disclosure} were higher than {prep} {run_name}{time_phrase} by {diff_str}:"

        bullets = [
            f"* {lead_name}: {lead_val_str}",
            f"* {run_name}: {run_val_str}",
            f"* Difference: {diff_str} (+{diff_pct:.2f}%)"
        ]
        for r in sorted_recs[2:]:
            r_val = r.get(val_key, 0.0)
            bullets.insert(-1, f"* {r['country']}: {format_metric(r_val, metrics)}")

        # Section 27: Comparative Insight Generation
        insight_sentence = ""
        if run_val > 0:
            ratio = lead_val / run_val
            combined = lead_val + run_val
            share_lead = (lead_val / combined * 100) if combined > 0 else 0.0

            if len(records) == 2:
                if ratio >= 1.5:
                    insight_sentence = f"{lead_name} accounts for {share_lead:.1f}% of the combined total, roughly {ratio:.1f}x larger than {run_name}."
            else:
                # 3+ entities
                insight_sentence = f"{lead_name} leads the second-place partner, {run_name}, by {diff_str} ({diff_pct:.1f}% higher)."

        base_msg = f"{header}\n\n" + "\n".join(bullets)
        if insight_sentence:
            return f"{base_msg}\n\n{insight_sentence}"
        return base_msg

    val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
    return f"Comparison of {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} was {format_metric(val_usd, metrics)}."
