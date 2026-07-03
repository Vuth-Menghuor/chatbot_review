import os
import json
import logging
from typing import Any, Dict
import httpx

logger = logging.getLogger(__name__)

from config import get_settings

def generate_message(facts: Dict[str, Any]) -> str:
    """Generate natural language message using LLM based on query results and user question."""
    settings = get_settings()
    
    # Dynamically build system instructions using data boundaries from Settings
    sys_instruction = (
        "You are a strict, BI-grade copywriter for a trade analytics chatbot.\n"
        "Your ONLY job is to directly answer the User Question using the provided JSON facts in a single, concise natural-language summary sentence.\n\n"
        "CRITICAL RULES:\n"
        "1. Directly address and answer the User Question using the provided JSON facts context.\n"
        "2. Do NOT calculate, compute, or infer any new values. Use the values as-is.\n"
        "3. Do NOT add external knowledge, geographical context, or historical comparisons.\n"
        "4. Keep the output to a single concise sentence.\n"
        "5. Do NOT use markdown code blocks or bullet points. Return plain text only.\n"
        "6. Write from Cambodia's perspective.\n"
        "7. Align your terminology and details with the User Question (e.g., if the user asks for \"Bottom 5\", describe the lowest partners; if the user asks for a monthly \"trend\", describe the monthly progression, peak, or overall pattern).\n"
        "8. NUMERICAL FORMATTING (STRICT): NEVER output raw, unformatted database floats (e.g., 31281322846.44). You MUST dynamically scale large numbers into human-readable text using \"million\" or \"billion\" rounded to two decimal places (e.g., format as \"$31.28 billion\" or \"89.20 million kg\"). Always include the correct currency symbol ($) or unit (kg).\n"
        "9. Use the most relevant facts from the provided JSON to fully answer the question. If multiple key values are returned (e.g., imports and exports for a total trade summary, or multiple categories requested by the user), naturally incorporate those values into the response instead of mentioning only one aggregated value.\n"
        "10. GROWTH INTENT RULE: For growth or decline questions, you must report the growth rate percentages (`growth_rate_pct`) per entity. NEVER sum or aggregate trade values (`VALUE_USD`) across different periods to report as a total trade value. Exclude entities or rows where `growth_rate_pct` is null (those represent baseline/earliest periods).\n"
        "11. TREND FLOW LABELING: For trend queries spanning both exports (EX) and imports (IM) (e.g. \"trade with China\", \"semester trend\", or \"last decade\"), you MUST describe and label both the export trend/values and the import trend/values separately and explicitly in your answer (e.g., write \"exports of $12.51 billion and imports of $13.95 billion\", never list them side-by-side as just \"$12.51 billion and $13.95 billion\" without labels).\n"
        "12. REPEATING PERIOD PATTERNS: If the facts indicate that a repeating sub-period pattern was requested (`repeating_period_pattern_requested` is True), you MUST explicitly state in the message that repeating sub-period patterns (like Q1 each year) are not supported by the system, and that a continuous range is being shown instead.\n"
        "13. TREND QUERY OVERRIDES: If the User Question contains a single year/period (e.g. \"in 2025\") but the intent is \"trend\" and multiple periods of data are provided in the JSON facts, you MUST summarize the entire trend across all provided periods (describing the progression, growth, or decline) rather than just snapshotting the single year mentioned in the question.\n"
        f"14. DATA BOUNDARY CAVEAT: If the facts indicate that the requested range exceeds available data (`data_boundary_exceeded` is True), you MUST append a brief caveat note to your message stating that data is only available from {settings.min_available_year} to {settings.max_available_year} (e.g. \"Note: trade data is only available for the {settings.min_available_year}–{settings.max_available_year} period.\").\n"
        "15. COMPARISON INTENT RULES:\n"
        "    a. EXPLICIT DIFFERENCE: When the User Question asks for a \"difference between\" two partners, you MUST explicitly compute and state the absolute difference in your answer (e.g. \"The difference is $5.3 billion\").\n"
        "    b. WINNER VERDICT: When the User Question asks \"which is bigger/larger/greater\" or \"who is the bigger trade partner\", you MUST explicitly name the larger partner and state the magnitude (e.g. \"China is the larger trade partner at $19.7 billion compared to Vietnam's $7.8 billion\").\n"
        "    c. TREND COMPARISON: When the comparison spans multiple periods (e.g. \"monthly trend\"), you MUST describe the progression for each partner, including peaks, troughs, and which partner was consistently higher.\n"
        "16. TRADE BALANCE INTENT RULES: For trade balance queries spanning multiple periods (e.g., monthly trend, last decade, over the years), you MUST explicitly summarize how the trade balance (surplus/deficit) progressed over time using the pre-calculated figures in `period_balances` (e.g. state that the deficit increased from $X to $Y, or a surplus turned into a deficit). Do not just state the export/import numbers separately; synthesize the balance progression."
    )

    api_key = os.getenv("X_GOOG_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.debug("No API key available for NLG generation. Using template fallback.")
        return _generate_fallback_template(facts)

    facts_copy = dict(facts)
    if facts_copy.get("intent") == "growth":
        # Remove period-spanning grand totals so LLM is forced to report growth rates instead of values
        facts_copy.pop("total_trade_value_usd", None)
        facts_copy.pop("subset_trade_value_usd", None)
        facts_copy.pop("total_weight_kg", None)
        facts_copy.pop("subset_weight_kg", None)

    model = os.getenv("GEMINI_MODEL", settings.default_gemini_model)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    question = facts_copy.get("question") or "N/A"
    prompt = (
        f"{sys_instruction}\n\n"
        f"User Question: \"{question}\"\n\n"
        f"JSON Facts:\n"
        f"{json.dumps(facts_copy, indent=2)}\n\n"
        f"Natural Language Summary:"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "text/plain",
            "maxOutputTokens": 256,
            "temperature": 0.2
        }
    }

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }

    try:
        logger.info(f"Invoking Gemini model '{model}' for NLG copywriting...")
        with httpx.Client(timeout=settings.default_timeout_sec) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            candidates = result.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned by LLM")

            content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if not content_text:
                raise ValueError("Empty response text from LLM")

            logger.info(f"NLG message generated successfully: '{content_text}'")
            return _append_data_quality_caveats(content_text, facts)

    except Exception as e:
        logger.warning(f"NLG LLM generation failed: {e}. Using fallback templates.", exc_info=True)
        return _append_data_quality_caveats(_generate_fallback_template(facts), facts)

def _append_data_quality_caveats(message: str, facts: Dict[str, Any]) -> str:
    """Ensure data quality and availability warnings are appended to the message."""
    dq = facts.get("data_quality") or {}
    notes = []

    # 1. Mismatch warning
    if dq.get("period_mismatch_note"):
        notes.append(dq["period_mismatch_note"])

    # 2. Range truncation warning
    if dq.get("period_coverage_note"):
        notes.append(dq["period_coverage_note"])

    # 3. Row limit truncation warning
    if dq.get("truncation_note"):
        notes.append(dq["truncation_note"])

    # 4. Partial/YTD year warning (only if not already in message)
    if dq.get("is_partial_period") and dq.get("partial_year_note"):
        note = dq["partial_year_note"]
        if note not in message:
            notes.append(note)

    if notes:
        # Strip trailing periods to format cleanly
        clean_notes = []
        for n in notes:
            if n not in message:
                clean_notes.append(n.strip().rstrip("."))
        if clean_notes:
            msg_clean = message.strip().rstrip(".")
            return f"{msg_clean}. ({'; '.join(clean_notes)}.)"
    return message

def _format_usd(val: float) -> str:
    """Format USD value to a human readable abbreviation."""
    if val >= 1e9:
        return f"${val / 1e9:.2f} billion"
    elif val >= 1e6:
        return f"${val / 1e6:.2f} million"
    elif val > 0:
        return f"${val:,.2f}"
    return "$0.00"

def _format_weight(val: float) -> str:
    """Format kg value to a human readable abbreviation."""
    if val >= 1e6:
        return f"{val / 1e6:,.2f} million kg"
    elif val > 0:
        return f"{val:,.2f} kg"
    return "0 kg"

def _format_metric(value: float, metrics: list[str], value_col: str = "") -> str:
    """Format value based on requested metrics (weight vs value)."""
    if value_col and "weight" in value_col.lower():
        return _format_weight(value)
    if any("weight" in str(m).lower() for m in metrics):
        return _format_weight(value)
    return _format_usd(value)

def _generate_capped_list_message(records, label_col="label", value_col="trade_value_usd", top_n_to_name=5, metrics=None):
    total_count = len(records)
    if total_count == 0:
        return ""
    named_items = records[:top_n_to_name]

    def get_label(r):
        lbl = r.get(label_col) or "Unknown"
        if isinstance(lbl, str):
            lbl = lbl.strip().replace('\r', '').replace('\n', '').strip()
        return lbl

    if len(named_items) == 1:
        lbl = get_label(named_items[0])
        val = named_items[0].get(value_col) or 0.0
        val_str = _format_metric(val, metrics or ["VALUE_USD"], value_col=value_col)
        return f"led by {lbl} at {val_str}"

    item_phrases = []
    for r in named_items:
        lbl = get_label(r)
        val = r.get(value_col) or 0.0
        val_str = _format_metric(val, metrics or ["VALUE_USD"], value_col=value_col)
        item_phrases.append(f"{lbl} at {val_str}")

    summary_phrase = ", ".join(item_phrases[:-1]) + f", and {item_phrases[-1]}"
    if total_count > top_n_to_name:
        return f"led by {summary_phrase}, among the top {total_count} shown below"
    return f"led by {summary_phrase}"

def _generate_ranking_message(records, label_col="label", value_col="trade_value_usd", top_n_to_name=5, metrics=None):
    return _generate_capped_list_message(records, label_col, value_col, top_n_to_name, metrics)

def _get_direction_phrase(flow: str, partner: Any) -> str:
    """Get dynamic phrase for flow direction and partner country."""
    if flow == "export":
        flow_phrase = "Exports"
        prep = "to"
    elif flow == "import":
        flow_phrase = "Imports"
        prep = "from"
    else:
        flow_phrase = "Total trade"
        prep = "with"

    if not partner:
        return flow_phrase

    if isinstance(partner, list):
        partner_str = ", ".join(partner)
    else:
        partner_str = str(partner)

    return f"{flow_phrase} {prep} {partner_str}"

def _get_product_phrase(facts: Dict[str, Any]) -> str:
    """Format product label dynamically."""
    prod = facts.get("sitc_division") or facts.get("sitc_section") or facts.get("hs_code") or facts.get("hs_chapter")
    if prod:
        from core.product_resolver import resolve_hs_to_name
        friendly = resolve_hs_to_name(str(prod))
        if friendly:
            return f" of {friendly}"

        if facts.get("sitc_division"):
            return f" of SITC Division {prod}"
        if facts.get("sitc_section"):
            return f" of SITC Section {prod}"
        if facts.get("hs_code"):
            return f" of HS Code {prod}"
        return f" of HS Chapter {prod}"
    return ""

def _get_transport_phrase(transport: Any) -> str:
    """Get transport phrase if present."""
    if transport:
        return f" via {transport}"
    return ""

def _generate_fallback_template(facts: Dict[str, Any]) -> str:
    """Deterministic fallback summary generator based on dynamic intent templates."""
    intent = facts.get("intent", "summary")
    flow = facts.get("flow", "trade")
    partner = facts.get("partner_country")
    period = facts.get("period") or "the selected period"
    transport = facts.get("mode_of_transport")
    metrics = facts.get("metrics") or ["VALUE_USD"]

    flow_phrase = _get_direction_phrase(flow, partner)
    prod_phrase = _get_product_phrase(facts)
    trans_phrase = _get_transport_phrase(transport)

    # Build a YTD suffix whenever the data is for the current in-progress year
    # and the user didn't specify a year (defaulted by the system).
    is_partial = facts.get("is_current_year_partial", False)
    ytd_suffix = f" (year-to-date — data for {period} is still in progress)" if is_partial else ""

    # Avoid double prepositions (e.g. "in from 2024...")
    if period and any(str(period).strip().lower().startswith(word) for word in ["from", "since", "until"]):
        time_phrase = f" {period}"
    else:
        time_phrase = f" in {period}"

    # 1. SUMMARY INTENT
    if intent == "summary":
        val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        weight = facts.get("total_weight_kg") or facts.get("subset_weight_kg") or 0.0
        val_formatted = _format_usd(val_usd)

        # Plural verb alignment
        verb = "were" if flow in ["export", "import"] else "was"

        balance_suffix = ""
        if facts.get("has_both_flows") and facts.get("trade_balance") is not None:
            tb = float(facts["trade_balance"])
            tb_type = "surplus" if tb >= 0 else "deficit"
            tb_formatted = _format_usd(abs(tb))
            balance_suffix = f" (a {tb_type} of {tb_formatted})"

        if "NET_WEIGHT" in metrics or facts.get("total_weight_kg") or facts.get("subset_weight_kg"):
            weight_str = _format_weight(weight)
            if "NET_WEIGHT" in metrics and "VALUE_USD" not in metrics:
                return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} {verb} {weight_str}{ytd_suffix}."
            return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} {verb} {val_formatted} (Net Weight: {weight_str}){balance_suffix}{ytd_suffix}."
        return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} {verb} {val_formatted}{balance_suffix}{ytd_suffix}."

    # 2. RANKING INTENT
    elif intent == "ranking":
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
            val_str = _format_metric(val, metrics, value_col=value_col)
            direction_word = "highest" if str(sort_order).lower() != "asc" else "lowest"
            period_text = f" in {period}" if period and period != "the selected period" else ""
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
        subset_count = facts.get("subset_count") or len(records)
        subset_label = facts.get("subset_label") or (f"top {limit}" if str(sort_order).lower() != "asc" else f"bottom {limit}")

        val_formatted = _format_metric(subset_val, metrics, value_col=value_col)
        subset_phrase = f"among Cambodia's {scope_phrase} {entity_label_plural}, the {subset_label} shown here total {val_formatted}, "

        # Truncation-capped summary phrase (Section 14)
        summary_details = _generate_ranking_message(records, label_col="label", value_col=value_col, top_n_to_name=5, metrics=metrics)
        summary_sentence = f"{message_prefix}{subset_phrase}{summary_details}."

        # Build the detailed list items below
        list_items = []
        for i, r in enumerate(records[:limit]):
            lbl = r.get("label") or "Unknown"
            val = r.get(value_col, 0.0)
            val_str = _format_metric(val, metrics, value_col=value_col)
            list_items.append(f"{i+1}. {lbl} ({val_str})")

        if not list_items:
            return f"No ranking records found for {period}."

        return f"{summary_sentence}\n\n" + "\n".join(list_items)

    # 3. TREND INTENT
    elif intent == "trend":
        records = facts.get("trend_records") or []
        if not records:
            val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
            return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {period} was {_format_metric(val_usd, metrics)}."

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
                return f"Cambodia's trade{partner_phrase} in {p} showed exports of {_format_metric(p_ex, metrics)} and imports of {_format_metric(p_im, metrics)}."
            else:
                start_p = distinct_periods[0]
                end_p = distinct_periods[-1]
                header = f"Cambodia's trade{partner_phrase} from {start_p} to {end_p} showed distinct export and import flows:"
                bullets = []
                for p in distinct_periods:
                    p_ex = grouped_periods[p].get("EX", 0.0)
                    p_im = grouped_periods[p].get("IM", 0.0)
                    bullets.append(f"* {p}: Exports {_format_metric(p_ex, metrics)}, Imports {_format_metric(p_im, metrics)}")
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
            
        header = f"From {start_p} to {end_p}, Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} {movement} from {_format_metric(start_val, metrics)} to {_format_metric(end_val, metrics)}:"
        
        bullets = []
        show_records = records
        if len(records) > 5:
            show_records = [records[0], records[len(records)//2], records[-1]]
            
        for r in show_records:
            p_label = r["period"]
            p_val = r["trade_value_usd"]
            bullets.append(f"* {p_label}: {_format_metric(p_val, metrics)}")
            
        return f"{header}\n\n" + "\n".join(bullets)

    # 4. COMPARISON INTENT
    elif intent == "comparison":
        records = facts.get("comparison_records") or []
        question_lower = str(facts.get("question", "")).lower()

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
                from collections import defaultdict
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
                    peak_phrase = f"peaking at {_format_metric(max_val, metrics)} in {max_period}" if max_period else f"peaking at {_format_metric(max_val, metrics)}"
                    trough_phrase = f"and reaching a low of {_format_metric(min_val, metrics)} in {min_period}" if min_period else f"and a low of {_format_metric(min_val, metrics)}"
                    trend_parts.append(f"{c} ranged from {_format_metric(min_val, metrics)} to {_format_metric(max_val, metrics)} ({peak_phrase}, {trough_phrase})")

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

            lead_val_str = _format_metric(lead_val, metrics)
            run_val_str = _format_metric(run_val, metrics)
            diff_str = _format_metric(diff, metrics)

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
                return f"{lead_name} is Cambodia's larger trade partner{prod_phrase}{time_phrase} with {_format_metric(lead_val, metrics)} {prep} {lead_name}, compared to {_format_metric(run_val, metrics)} {prep} {run_name}."

            if asks_difference and len(records) == 2:
                return f"The difference in {flow_word.lower()}{prod_phrase} between {lead_name} and {run_name}{time_phrase} is {diff_str}: {_format_metric(lead_val, metrics)} for {lead_name} versus {_format_metric(run_val, metrics)} for {run_name}."

            header = f"{flow_word}{prod_phrase} {prep} {lead_name}{metric_disclosure} were higher than {prep} {run_name}{time_phrase} by {diff_str}:"

            bullets = [
                f"* {lead_name}: {lead_val_str}",
                f"* {run_name}: {run_val_str}",
                f"* Difference: {diff_str} (+{diff_pct:.2f}%)"
            ]
            for r in sorted_recs[2:]:
                r_val = r.get(val_key, 0.0)
                bullets.insert(-1, f"* {r['country']}: {_format_metric(r_val, metrics)}")

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
        return f"Comparison of {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} was {_format_metric(val_usd, metrics)}."

    # 5. BREAKDOWN INTENT
    elif intent == "breakdown":
        breakdown_records = facts.get("group_breakdown_records") or facts.get("mode_breakdown_records") or []
        grouped_by = facts.get("grouped_by", "group")
        
        if breakdown_records:
            total_val = sum(r["trade_value_usd"] for r in breakdown_records)
            
            summary_details = _generate_capped_list_message(breakdown_records, label_col="label", value_col="trade_value_usd", top_n_to_name=5, metrics=metrics)
            
            limit = facts.get("limit") or len(breakdown_records)
            total_count = len(breakdown_records)
            subset_val = facts.get("subset_total_value") or total_val
            val_formatted = _format_metric(subset_val, metrics)
            
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
                bullets.append(f"* {lbl}: {_format_metric(val, metrics)} ({share:.1f}%)")
                
            if len(breakdown_records) > show_limit:
                other_val = sum(r["trade_value_usd"] for r in breakdown_records[show_limit:])
                other_share = (other_val / total_val * 100) if total_val > 0 else 0.0
                bullets.append(f"* Others: {_format_metric(other_val, metrics)} ({other_share:.1f}%)")
                
            return f"{header}{concentration_insight}\n\n" + "\n".join(bullets)
            
        val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        return f"Breakdown of {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} totaled {_format_metric(val_usd, metrics)}."

    # 6. GROWTH INTENT
    # Reads data_quality["growth_valid"] as the SOLE truth flag (Section 19).
    # intent is always "growth" here — reads execution_mode for degraded fallback.
    # Never states a percentage when growth_rate_pct is None (Section 19).
    # Uses directional_context for decline confirmation/correction (Section 21).
    elif intent == "growth":
        data_quality = facts.get("data_quality") or {}
        growth_valid = data_quality.get("growth_valid", False)
        execution_mode = facts.get("execution_mode", "growth")
        directional_context = facts.get("directional_context") or facts.get("extra", {}).get("directional_context")

        # Degraded fallback:
        if not growth_valid or execution_mode != "growth":
            downgrade_reason = facts.get("growth_downgrade_reason", "Baseline period data was not available.")
            val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
            val_str = _format_metric(val_usd, metrics) if val_usd else "unavailable"
            return (
                f"Growth rate could not be computed for Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase}: "
                f"{downgrade_reason} "
                f"The most recent available value was {val_str}."
            )

        records = facts.get("growth_records") or []
        
        # 1. Identify the entity grouping key
        entity_key = None
        if records:
            for key in ["PARTNER_COUNTRY", "partner_country", "HS_HEADING", "hs_heading", 
                        "SITC_DIVISION", "sitc_division", "MODE_OF_TRANSPORT", "mode_of_transport",
                        "HS_CHAPTER", "hs_chapter", "FLOW", "flow"]:
                if key in records[0]:
                    entity_key = key
                    break

        # 2. Group records by entity
        entity_groups = {}
        if entity_key:
            for r in records:
                ent = r.get(entity_key)
                if ent is not None:
                    entity_groups.setdefault(ent, []).append(r)
        else:
            entity_groups["Cambodia"] = records

        # 3. Find latest rows and new entrants
        latest_rows = []
        new_entrants = []
        for ent, ent_records in entity_groups.items():
            ent_records.sort(key=lambda x: str(x.get("period", "")))
            lat_r = next((r for r in reversed(ent_records) if r.get("growth_rate_pct") is not None), None)
            if lat_r:
                latest_rows.append(lat_r)
            else:
                new_entrants.append(str(ent))

        # Sort latest_rows according to Rule 3
        question_lower = facts.get("question", "").lower()
        is_fastest = any(kw in question_lower for kw in ["fastest", "rapid", "highest growth", "most growth"])
        
        if is_fastest:
            latest_rows.sort(key=lambda x: abs(x.get("growth_rate_pct") or 0.0), reverse=True)
        else:
            latest_rows.sort(key=lambda x: x.get("trade_value_usd", 0.0), reverse=True)

        all_periods = sorted(list(set(str(r.get("period")) for r in records if r.get("period"))))
        
        # 5. Output generation
        # Single-entity path
        if len(entity_groups) <= 1 or len(latest_rows) <= 1:
            if not latest_rows:
                return f"No growth records with baseline data were found."
            
            latest = latest_rows[0]
            ent = latest.get(entity_key) if entity_key else None
            ent_recs = sorted(entity_groups[ent] if ent else records, key=lambda x: str(x.get("period", "")))
            
            rate = latest.get("growth_rate_pct")
            val_latest_str = _format_metric(latest.get("trade_value_usd", 0.0), metrics)
            val_start_str = _format_metric(ent_recs[0].get("trade_value_usd", 0.0), metrics)
            
            # Directional template
            flow_lc = flow_phrase.strip().lower()
            if directional_context == "decline":
                if rate is not None and rate < 0:
                    return f"Yes, {flow_lc}{prod_phrase}{trans_phrase} declined by {abs(rate):.2f}% from {val_start_str} to {val_latest_str}."
                elif rate is not None:
                    return f"No, {flow_lc}{prod_phrase}{trans_phrase} actually increased by {rate:.2f}%, not declined."

            # 3-period single-entity template
            if len(all_periods) >= 3:
                steps = []
                for i in range(1, len(ent_recs)):
                    curr = ent_recs[i]
                    r = curr.get("growth_rate_pct")
                    if r is not None:
                        status = "grew" if r >= 0 else "declined"
                        steps.append(f"{status} {abs(r):.2f}% in {curr.get('period')}")
                steps_phrase = ", then ".join(steps)
                return f"Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} {steps_phrase} (from {val_start_str} to {val_latest_str})."

            # 2-period single-entity template
            year1 = ent_recs[0].get("period", "")
            year2 = latest.get("period", "")
            status_word = "grew" if rate >= 0 else "declined"
            return f"Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} {status_word} from {val_start_str} in {year1} to {val_latest_str} in {year2}, a growth rate of {rate:+.2f}%."

        # Multi-entity path
        else:
            start_year = all_periods[0] if all_periods else ""
            end_year = all_periods[-1] if all_periods else ""
            
            header = f"From {start_year} to {end_year}, Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} grew across top partners:"
            if "import" in flow_phrase.lower():
                header = f"From {start_year} to {end_year}, Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} grew across top import sources:"
            elif "export" in flow_phrase.lower():
                header = f"From {start_year} to {end_year}, Cambodia's {flow_phrase.strip()}{prod_phrase}{trans_phrase} grew across top export destinations:"
                
            bullets = []
            for r in latest_rows:
                ent = r.get(entity_key)
                rate = r.get("growth_rate_pct", 0.0)
                val_end = r.get("trade_value_usd", 0.0)
                
                ent_recs = sorted(entity_groups[ent], key=lambda x: str(x.get("period", "")))
                val_start = ent_recs[0].get("trade_value_usd", 0.0)
                
                val_start_str = _format_metric(val_start, metrics)
                val_end_str = _format_metric(val_end, metrics)
                
                # 3-period multi-entity step formatting (Rule 5)
                if len(all_periods) >= 3:
                    steps = []
                    for i in range(1, len(ent_recs)):
                        curr = ent_recs[i]
                        step_rate = curr.get("growth_rate_pct")
                        if step_rate is not None:
                            status_abbr = "+" if step_rate >= 0 else ""
                            steps.append(f"{status_abbr}{step_rate:.2f}% in {curr.get('period')}")
                    steps_phrase = ", then ".join(steps)
                    bullets.append(f"* {ent}: {steps_phrase} ({val_start_str} → {val_end_str})")
                else:
                    bullets.append(f"* {ent}: {rate:+.2f}% ({val_start_str} → {val_end_str})")

            new_entrants_phrase = ""
            if new_entrants:
                new_entrants_phrase = f"\n\nNew entrants (no prior year data): {', '.join(new_entrants)}."

            return f"{header}\n" + "\n".join(bullets) + new_entrants_phrase


    # 7. TRADE_BALANCE INTENT
    elif intent == "trade_balance":
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
                header = f"From {start_p} to {end_p}, Cambodia's trade balance{partner_suffix} moved from a {s_status} of {_format_usd(abs(s_bal))} to a {e_status} of {_format_usd(abs(e_bal))}:"
                
                bullets = []
                show_periods = sorted_periods
                if len(sorted_periods) > 5:
                    show_periods = [sorted_periods[0], sorted_periods[len(sorted_periods)//2], sorted_periods[-1]]
                    
                for p in show_periods:
                    p_ex = period_data[p]["EX"]
                    p_im = period_data[p]["IM"]
                    p_bal = p_ex - p_im
                    p_status = "Surplus" if p_bal >= 0 else "Deficit"
                    bullets.append(f"* {p}: {_format_usd(abs(p_bal))} ({p_status}) [Exports: {_format_usd(p_ex)}, Imports: {_format_usd(p_im)}]")
                    
                return f"{header}\n\n" + "\n".join(bullets)

        exports = facts.get("total_exports_usd") or 0.0
        imports = facts.get("total_imports_usd") or 0.0
        
        if exports == 0.0 and imports == 0.0:
            if flow == "export":
                exports = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
            elif flow == "import":
                imports = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
                
        balance = exports - imports
        bal_str = _format_usd(abs(balance))
        status = "surplus" if balance >= 0 else "deficit"
        
        partner_phrase = f" with {partner}" if partner else ""
        header = f"In {period}, Cambodia recorded a trade {status} of {bal_str}{partner_phrase}, driven by {_format_usd(exports)} in exports against {_format_usd(imports)} in imports."
        
        bullets = [
            f"* Exports: {_format_usd(exports)}",
            f"* Imports: {_format_usd(imports)}",
            f"* Trade {status.capitalize()}: {bal_str}"
        ]
        return f"{header}\n\n" + "\n".join(bullets)

    val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
    verb = "were" if flow in ["export", "import"] else "was"
    return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} {verb} {_format_metric(val_usd, metrics)}."