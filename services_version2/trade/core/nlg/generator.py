import os
import json
import logging
from typing import Any, Dict
import httpx

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_TIMEOUT_SEC = 10  # Keep NLG generation quick to avoid query delays but allow sufficient time

SYSTEM_INSTRUCTION = """You are a strict, BI-grade copywriter for a trade analytics chatbot.
Your ONLY job is to translate the provided JSON facts into a single, concise natural-language summary sentence.

CRITICAL RULES:
1. Do NOT calculate, compute, or infer any new values. Use the values as-is.
2. Do NOT add external knowledge, geographical context, or historical comparisons.
3. Keep the output to a single concise sentence (under 30 words).
4. Do NOT use markdown code blocks or bullet points. Return plain text only.
5. If the facts show multiple records (e.g. comparison/ranking/group_breakdown), summarize the main points concisely.
6. If "group_breakdown_records" or "mode_breakdown_records" is present, explicitly name and compare at least the top
   two groups by trade_value_usd (e.g. "Sea transport ($X) outpaced Air transport ($Y)..."), rather than reporting
   only an aggregate total.
7. Write from Cambodia's perspective.
"""

def generate_message(facts: Dict[str, Any]) -> str:
    """Generate natural language message using fallback templates, or use LLM if enabled."""
    if os.getenv("USE_LLM_NLG", "false").lower() != "true":
        logger.info("Structured NLG templates are enabled. Skipping LLM generation.")
        return _generate_fallback_template(facts)

    api_key = os.getenv("X_GOOG_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.debug("No API key available for NLG generation. Using template fallback.")
        return _generate_fallback_template(facts)

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    prompt = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"JSON Facts:\n"
        f"{json.dumps(facts, indent=2)}\n\n"
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
            "maxOutputTokens": 100,
            "temperature": 0.2
        }
    }

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }

    try:
        logger.info(f"Invoking Gemini model '{model}' for NLG copywriting...")
        with httpx.Client(timeout=DEFAULT_TIMEOUT_SEC) as client:
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
            return content_text

    except Exception as e:
        logger.warning(f"NLG LLM generation failed: {e}. Using fallback templates.", exc_info=True)
        return _generate_fallback_template(facts)

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

def _format_metric(value: float, metrics: list[str]) -> str:
    """Format value based on requested metrics (weight vs value)."""
    if any("weight" in str(m).lower() for m in metrics):
        return _format_weight(value)
    return _format_usd(value)

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
    prod = facts.get("hs_code") or facts.get("hs_chapter")
    if prod:
        if str(prod).isdigit():
            if len(str(prod)) <= 2:
                return f" of HS Chapter {prod}"
            return f" of HS Code {prod}"
        return f" of {prod}"
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

    # 1. SUMMARY INTENT
    if intent == "summary":
        val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        weight = facts.get("total_weight_kg") or facts.get("subset_weight_kg") or 0.0
        val_formatted = _format_metric(val_usd, metrics)

        if "NET_WEIGHT" in metrics or facts.get("total_weight_kg") or facts.get("subset_weight_kg"):
            weight_str = _format_weight(weight)
            if "NET_WEIGHT" in metrics and "VALUE_USD" not in metrics:
                return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {period} was {weight_str}."
            return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {period} was {val_formatted} (Net Weight: {weight_str})."
        return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {period} was {val_formatted}."

    # 2. RANKING INTENT
    elif intent == "ranking":
        records = facts.get("ranking_records") or []
        sort_order = facts.get("sort_order", "desc")
        limit = facts.get("limit") or len(records)
        
        dir_word = "lowest" if sort_order == "asc" else "highest"
        flow_word = "import" if flow == "import" else "export" if flow == "export" else "trade"
        
        grouping_word = "partner countries"
        if records:
            first_lbl = str(records[0].get("label", ""))
            if first_lbl.lower() in ["air", "sea", "land", "inland water", "rail", "postal", "multimodal"]:
                grouping_word = "transport modes"
            elif first_lbl.isdigit():
                grouping_word = "product chapters/headings"
        
        partner_suffix = f" with {partner}" if partner else ""
        header = f"The {limit} {grouping_word} with the {dir_word} {flow_word} values{prod_phrase}{trans_phrase}{partner_suffix} in {period} were:"
        
        list_items = []
        for i, r in enumerate(records[:limit]):
            lbl = r.get("label") or "Unknown"
            val = r.get("trade_value_usd", 0.0)
            val_str = _format_metric(val, metrics)
            list_items.append(f"{i+1}. {lbl} ({val_str})")
        
        if not list_items:
            return f"No ranking records found for {period}."
        return f"{header}\n\n" + "\n".join(list_items)

    # 3. TREND INTENT
    elif intent == "trend":
        records = facts.get("trend_records") or []
        if not records:
            val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
            return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {period} was {_format_metric(val_usd, metrics)}."

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
        if len(records) >= 2:
            sorted_recs = sorted(records, key=lambda x: x["trade_value_usd"], reverse=True)
            leader = sorted_recs[0]
            runner_up = sorted_recs[1]
            
            lead_name = leader["country"]
            run_name = runner_up["country"]
            
            lead_val = leader["trade_value_usd"]
            run_val = runner_up["trade_value_usd"]
            
            diff = lead_val - run_val
            diff_pct = (diff / run_val * 100) if run_val > 0 else 0.0
            
            lead_val_str = _format_metric(lead_val, metrics)
            run_val_str = _format_metric(run_val, metrics)
            diff_str = _format_metric(diff, metrics)
            
            flow_word = "Exports" if flow == "export" else "Imports" if flow == "import" else "Trade"
            
            header = f"{flow_word}{prod_phrase} to {lead_name} were higher than to {run_name} in {period} by {diff_str}:"
            if flow == "import":
                header = f"{flow_word}{prod_phrase} from {lead_name} were higher than from {run_name} in {period} by {diff_str}:"
                
            bullets = [
                f"* {lead_name}: {lead_val_str}",
                f"* {run_name}: {run_val_str}",
                f"* Difference: {diff_str} (+{diff_pct:.2f}%)"
            ]
            for r in sorted_recs[2:]:
                bullets.insert(-1, f"* {r['country']}: {_format_metric(r['trade_value_usd'], metrics)}")
                
            return f"{header}\n\n" + "\n".join(bullets)
            
        val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        return f"Comparison of {flow_phrase}{prod_phrase}{trans_phrase} in {period} was {_format_metric(val_usd, metrics)}."

    # 5. BREAKDOWN INTENT
    elif intent == "breakdown":
        breakdown_records = facts.get("group_breakdown_records") or facts.get("mode_breakdown_records") or []
        grouped_by = facts.get("grouped_by", "group")
        
        if breakdown_records:
            total_val = sum(r["trade_value_usd"] for r in breakdown_records)
            leader = breakdown_records[0]
            leader_name = leader["label"].capitalize() if isinstance(leader["label"], str) else str(leader["label"])
            
            header = f"Cambodia's {flow_phrase}{prod_phrase} in {period} broken down by {grouped_by} was primarily concentrated in {leader_name}:"
            
            bullets = []
            for r in breakdown_records[:5]:
                lbl = r["label"].capitalize() if isinstance(r["label"], str) else str(r["label"])
                val = r["trade_value_usd"]
                share = (val / total_val * 100) if total_val > 0 else 0.0
                bullets.append(f"* {lbl}: {_format_metric(val, metrics)} ({share:.1f}%)")
                
            if len(breakdown_records) > 5:
                other_val = sum(r["trade_value_usd"] for r in breakdown_records[5:])
                other_share = (other_val / total_val * 100) if total_val > 0 else 0.0
                bullets.append(f"* Others: {_format_metric(other_val, metrics)} ({other_share:.1f}%)")
                
            return f"{header}\n\n" + "\n".join(bullets)
            
        val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        return f"Breakdown of {flow_phrase}{prod_phrase}{trans_phrase} in {period} totaled {_format_metric(val_usd, metrics)}."

    # 6. GROWTH INTENT
    elif intent == "growth":
        records = facts.get("growth_records") or []
        if len(records) >= 2:
            latest = records[-1]
            prev = records[-2]
            
            late_p = latest["period"]
            prev_p = prev["period"]
            
            late_val = latest["trade_value_usd"]
            prev_val = prev["trade_value_usd"]
            
            rate = latest.get("growth_rate_pct", 0.0)
            if rate == 0.0 and prev_val > 0:
                rate = round(((late_val - prev_val) / prev_val) * 100, 2)
                
            status = "grew" if rate >= 0 else "declined"
            verb = "+" if rate >= 0 else ""
            diff = late_val - prev_val
            
            header = f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {late_p} {status} by {abs(rate)}% compared to {prev_p}:"
            
            bullets = [
                f"* {late_p}: {_format_metric(late_val, metrics)}",
                f"* {prev_p}: {_format_metric(prev_val, metrics)}",
                f"* Change: {verb}{_format_metric(diff, metrics)} ({verb}{rate:.2f}%)"
            ]
            return f"{header}\n\n" + "\n".join(bullets)
            
        elif records:
            latest = records[-1]
            rate = latest.get("growth_rate_pct", 0.0)
            status = "grew" if rate >= 0 else "declined"
            return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {latest['period']} was {_format_metric(latest['trade_value_usd'], metrics)} ({status} by {rate}%)."
            
        val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
        return f"Trade growth analysis for {period} returned value of {_format_metric(val_usd, metrics)}."

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
                    bullets.append(f"* {p}: {_format_usd(p_bal)} ({p_status}) [Exports: {_format_usd(p_ex)}, Imports: {_format_usd(p_im)}]")
                    
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
        
        partner_suffix = f" with {partner}" if partner else ""
        header = f"Cambodia recorded a trade {status} of {bal_str}{partner_suffix} in {period}:"
        
        bullets = [
            f"* Exports: {_format_usd(exports)}",
            f"* Imports: {_format_usd(imports)}",
            f"* Net Balance: {bal_str} ({status.capitalize()})"
        ]
        return f"{header}\n\n" + "\n".join(bullets)

    val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
    return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase} in {period} was {_format_metric(val_usd, metrics)}."