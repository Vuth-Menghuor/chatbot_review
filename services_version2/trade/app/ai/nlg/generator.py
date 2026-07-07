import json
import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

from app.core.config import get_settings


def generate_message(facts: Dict[str, Any]) -> str:
    """Generate natural language message using LLM based on query results and user question."""
    settings = get_settings()

    # Dynamically build system instructions using data boundaries from Settings
    from app.core.prompt_service import DynamicPromptManager
    manager = DynamicPromptManager(prompts_dir=settings.prompts_dir)
    sys_instruction_template = manager.get_system_prompt("nlg_copywriter")
    sys_instruction = sys_instruction_template.format(
        min_available_year=settings.min_available_year,
        max_available_year=settings.max_available_year
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

def _generate_fallback_template(facts: Dict[str, Any]) -> str:
    """Deterministic fallback summary generator based on dynamic intent templates."""
    intent = facts.get("intent", "summary")
    flow = facts.get("flow", "trade")
    partner = facts.get("partner_country")
    period = facts.get("period") or "the selected period"
    transport = facts.get("mode_of_transport")
    metrics = facts.get("metrics") or ["VALUE_USD"]

    from app.ai.nlg.format_utils import (
        format_metric,
        get_direction_phrase,
        get_product_phrase,
        get_transport_phrase,
    )
    from app.ai.nlg.templates import (
        render_breakdown,
        render_comparison,
        render_growth,
        render_ranking,
        render_summary,
        render_trade_balance,
        render_trend,
    )

    flow_phrase = get_direction_phrase(flow, partner)
    prod_phrase = get_product_phrase(facts)
    trans_phrase = get_transport_phrase(transport)

    # Build a YTD suffix whenever the data is for the current in-progress year
    # and the user didn't specify a year (defaulted by the system).
    is_partial = facts.get("is_current_year_partial", False)
    ytd_suffix = f" (year-to-date — data for {period} is still in progress)" if is_partial else ""

    # Avoid double prepositions (e.g. "in from 2024...")
    if period and any(str(period).strip().lower().startswith(word) for word in ["from", "since", "until"]):
        time_phrase = f" {period}"
    else:
        time_phrase = f" in {period}"

    if intent == "summary":
        return render_summary(
            facts=facts,
            flow_phrase=flow_phrase,
            prod_phrase=prod_phrase,
            trans_phrase=trans_phrase,
            time_phrase=time_phrase,
            ytd_suffix=ytd_suffix,
        )
    elif intent == "ranking":
        return render_ranking(
            facts=facts,
            period=period,
            metrics=metrics,
        )
    elif intent == "trend":
        return render_trend(
            facts=facts,
            flow_phrase=flow_phrase,
            prod_phrase=prod_phrase,
            trans_phrase=trans_phrase,
            period=period,
            partner=partner,
            metrics=metrics,
        )
    elif intent == "comparison":
        return render_comparison(
            facts=facts,
            flow_phrase=flow_phrase,
            prod_phrase=prod_phrase,
            trans_phrase=trans_phrase,
            time_phrase=time_phrase,
            flow=flow,
            metrics=metrics,
            question_lower=str(facts.get("question", "")).lower(),
        )
    elif intent == "breakdown":
        return render_breakdown(
            facts=facts,
            flow_phrase=flow_phrase,
            prod_phrase=prod_phrase,
            trans_phrase=trans_phrase,
            time_phrase=time_phrase,
            flow=flow,
            metrics=metrics,
        )
    elif intent == "growth":
        return render_growth(
            facts=facts,
            flow_phrase=flow_phrase,
            prod_phrase=prod_phrase,
            trans_phrase=trans_phrase,
            metrics=metrics,
        )
    elif intent == "trade_balance":
        return render_trade_balance(
            facts=facts,
            flow_phrase=flow_phrase,
            prod_phrase=prod_phrase,
            trans_phrase=trans_phrase,
            period=period,
            partner=partner,
            flow=flow,
        )

    val_usd = facts.get("total_trade_value_usd") or facts.get("subset_trade_value_usd") or 0.0
    verb = "were" if flow in ["export", "import"] else "was"
    return f"Cambodia's {flow_phrase}{prod_phrase}{trans_phrase}{time_phrase} {verb} {format_metric(val_usd, metrics)}."
