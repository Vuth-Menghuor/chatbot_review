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
    """Generate natural language message using Gemini API, falling back to templates on failure."""
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

def _generate_fallback_template(facts: Dict[str, Any]) -> str:
    """Deterministic fallback summary generator based on static intent templates."""
    intent = facts.get("intent", "summary")
    flow = facts.get("flow", "trade")
    partner = facts.get("partner_country")
    period = facts.get("period") or "the selected period"
    transport = facts.get("mode_of_transport")
    val_raw = facts.get("total_trade_value_usd", 0.0)

    partner_suffix = f" with {partner}" if partner else ""
    if isinstance(partner, list):
        partner_suffix = f" with {', '.join(partner)}"

    transport_suffix = f" via {transport}" if transport else ""
    val_str = _format_usd(val_raw)

    flow_cap = "Exports" if flow == "export" else "Imports" if flow == "import" else "Trade"

    # NEW: grouped breakdown takes priority over the flat total whenever
    # the query was grouped by a dimension (e.g. MODE_OF_TRANSPORT). This is
    # what previously fell through to the generic "Trade value... was $X"
    # template, hiding the per-group comparison the user actually asked for.
    breakdown_records = facts.get("mode_breakdown_records") or facts.get("group_breakdown_records")
    if breakdown_records:
        grouped_by = facts.get("grouped_by", "group")
        top = breakdown_records[:3]
        items_str = ", ".join(
            f"{r['label'].capitalize() if isinstance(r['label'], str) else r['label']}: {_format_usd(r['trade_value_usd'])}"
            for r in top
        )
        if len(top) >= 2:
            leader, runner_up = top[0], top[1]
            leader_name = leader['label'].capitalize() if isinstance(leader['label'], str) else leader['label']
            runner_name = runner_up['label'].capitalize() if isinstance(runner_up['label'], str) else runner_up['label']
            return (
                f"By {grouped_by}, Cambodia's {flow_cap.lower()}{partner_suffix} in {period} were led by "
                f"{leader_name} ({_format_usd(leader['trade_value_usd'])}), followed by "
                f"{runner_name} ({_format_usd(runner_up['trade_value_usd'])})."
            )
        return f"{flow_cap} value{partner_suffix} by {grouped_by} in {period}: {items_str}."

    if intent == "trade_balance":
        # Calculate balance manually if possible
        exports = 0.0
        imports = 0.0
        exports_raw = facts.get("total_exports_usd")
        imports_raw = facts.get("total_imports_usd")
        if exports_raw is not None and imports_raw is not None:
            exports = float(exports_raw)
            imports = float(imports_raw)
        else:
            if flow == "export":
                exports = val_raw
            elif flow == "import":
                imports = val_raw

        balance = exports - imports
        bal_str = _format_usd(abs(balance))
        status = "surplus" if balance >= 0 else "deficit"

        if partner:
            return f"Cambodia recorded a trade {status} of {bal_str} with {partner} in {period} (Exports: {_format_usd(exports)}, Imports: {_format_usd(imports)})."
        else:
            return f"Cambodia recorded a total trade {status} of {bal_str} in {period} (Exports: {_format_usd(exports)}, Imports: {_format_usd(imports)})."

    elif intent == "comparison":
        records = facts.get("comparison_records")
        if records:
            items_str = ", ".join(f"{r['country']}: {_format_usd(r['trade_value_usd'])}" for r in records[:3])
            return f"Comparison of {flow or 'trade'} value in {period}: {items_str}."
        return f"Comparison of {flow or 'trade'} value{partner_suffix} in {period} was {val_str}."

    elif intent == "ranking":
        records = facts.get("ranking_records")
        if records:
            items_str = ", ".join(f"{r['label']}: {_format_usd(r['trade_value_usd'])}" for r in records[:3])
            return f"Top trade records for {period}: {items_str}."
        return f"Top trade value for {period} was {val_str}."

    elif intent == "growth":
        records = facts.get("growth_records")
        if records:
            latest = records[-1]
            rate = latest.get("growth_rate_pct", 0.0)
            status = "grew" if rate >= 0 else "declined"
            return f"Trade value in {latest['period']} was {_format_usd(latest['trade_value_usd'])} which {status} by {abs(rate)}% compared to the previous period."
        return f"Trade growth analysis for {period} returned value of {val_str}."

    elif intent == "breakdown":
        return f"Breakdown of {flow_cap} value{partner_suffix}{transport_suffix} in {period} totaled {val_str}."

    # Summary or default trend fallbacks
    return f"{flow_cap} value{partner_suffix}{transport_suffix} in {period} was {val_str}."