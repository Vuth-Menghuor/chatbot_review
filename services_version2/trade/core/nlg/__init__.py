from typing import Any, Dict
from .formatters import extract_facts
from .generator import generate_message
from .suggestions import get_suggestions

def generate_nlg_response(payload: Dict[str, Any], query_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for Stage 6 (Natural Language Generation).

    Extracts raw facts from the payload, generates a copywriter summary,
    and appends next-step suggestions.

    Updates and returns the payload dictionary with:
    - payload["facts"]
    - payload["message"]
    - payload["suggestions"]
    """
    # 1. Extract raw facts from payload and query parameters
    facts = extract_facts(payload, query_params)

    # Intent-specific facts adjustments for trade balance
    intent = query_params.get("intent", "summary")
    if intent == "trade_balance":
        records = payload.get("records") or []
        exports_total = sum(float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0) for r in records if str(r.get("FLOW", "")).upper() == "EX")
        imports_total = sum(float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0) for r in records if str(r.get("FLOW", "")).upper() == "IM")
        facts["total_exports_usd"] = exports_total
        facts["total_imports_usd"] = imports_total
        facts["total_trade_value_usd"] = abs(exports_total - imports_total)  # net balance

    # 2. Call generator to draft the natural language message
    message = generate_message(facts)

    # 3. Generate follow-up suggestions
    suggestions = get_suggestions(facts, query_params)

    # 4. Attach to the payload for frontend consumption
    payload["facts"] = facts
    payload["message"] = message
    payload["suggestion"] = suggestions

    return payload