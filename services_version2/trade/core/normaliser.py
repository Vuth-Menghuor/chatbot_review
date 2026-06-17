"""Normalise raw DAL responses into the final JSON shape."""

from __future__ import annotations

from typing import Any

from ..handlers.scopes import get_scope_config
from .exceptions import NormalisationError


def normalise(
    dal_response: dict[str, Any],
    intent: str,
    query_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shape a raw DAL response into the standard TradeQueryResponse envelope."""

    if not isinstance(dal_response, dict):
        raise NormalisationError("DAL response must be a dict")

    records = dal_response.get("records") or dal_response.get("data") or []
    if not isinstance(records, list):
        records = [records]

    count = dal_response.get("count") or len(records)

    # Build summary from records if not provided
    summary = dal_response.get("summary") or {}
    if not summary and records:
        total_value = sum(
            float(r.get("VALUE_USD", r.get("trade_value", 0)) or 0)
            for r in records
        )
        summary = {"total_trade_value": total_value, "currency": "USD"}

    # Merge DAL metadata with scope metadata
    scope = get_scope_config(intent)
    metadata = dal_response.get("metadata") or {}
    metadata["intent"] = intent
    metadata["count"] = count
    metadata["scopes"] = {
        "query_intent": intent,
        "supported_dimensions": scope.dimensions,
        "supported_measures": scope.measures,
        "supported_capabilities": scope.capabilities,
        "suggested_visualizations": scope.visualizations,
    }

    # Generate frontend-ready visualization payloads
    from ..visualization import generate_visualizations
    viz_payload = generate_visualizations(records, intent, query_params)

    return {
        "status": "success",
        "count": count,
        "records": records,
        "summary": summary,
        "metadata": metadata,
        "table": viz_payload.get("table"),
        "visualization": viz_payload.get("visualization"),
        "total_trade_value": summary.get("total_trade_value"),
        "currency": summary.get("currency", "USD"),
    }
