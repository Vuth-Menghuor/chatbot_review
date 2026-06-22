"""Normalise raw DAL responses into the final JSON shape."""

from __future__ import annotations

from typing import Any

from ..handlers.scopes import get_scope_config
from .exceptions import NormalisationError


def compute_growth_rates(records: list[dict[str, Any]], query_params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Calculate period-over-period percentage growth rates for records."""
    value_key = "VALUE_USD"
    if query_params and query_params.get("metrics"):
        value_key = query_params["metrics"][0]

    period_key = None
    if records:
        for k in ["PERIOD", "period", "Period"]:
            if k in records[0]:
                period_key = k
                break

    if not period_key:
        return records

    group_key = None
    if query_params and query_params.get("group_by"):
        group_key = query_params["group_by"][0]
        if records:
            for k in records[0].keys():
                if k.lower() == group_key.lower():
                    group_key = k
                    break

    result_records = []
    if group_key and group_key != period_key:
        groups = {}
        for r in records:
            g_val = r.get(group_key)
            if g_val not in groups:
                groups[g_val] = []
            groups[g_val].append(r)

        for g_val, g_records in groups.items():
            g_records.sort(key=lambda x: str(x.get(period_key, "")))
            for i, r in enumerate(g_records):
                if i == 0:
                    r["growth_rate_pct"] = 0.0
                else:
                    prev_r = g_records[i - 1]
                    prev_val = float(prev_r.get(value_key) or 0)
                    curr_val = float(r.get(value_key) or 0)
                    if prev_val == 0:
                        r["growth_rate_pct"] = 0.0
                    else:
                        r["growth_rate_pct"] = round(((curr_val - prev_val) / prev_val) * 100, 2)
                result_records.append(r)

        periods = sorted(list(set(str(r.get(period_key, "")) for r in records if r.get(period_key) is not None)))
        if len(periods) > 1:
            latest_period = periods[-1]
            filtered_records = [r for r in result_records if str(r.get(period_key)) == latest_period]
            return filtered_records
        return result_records
    else:
        records_copy = [dict(r) for r in records]
        records_copy.sort(key=lambda x: str(x.get(period_key, "")))
        for i, r in enumerate(records_copy):
            if i == 0:
                r["growth_rate_pct"] = 0.0
            else:
                prev_r = records_copy[i - 1]
                prev_val = float(prev_r.get(value_key) or 0)
                curr_val = float(r.get(value_key) or 0)
                if prev_val == 0:
                    r["growth_rate_pct"] = 0.0
                else:
                    r["growth_rate_pct"] = round(((curr_val - prev_val) / prev_val) * 100, 2)
        return records_copy


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

    if intent == "growth" and records:
        records = compute_growth_rates(records, query_params)

    count = len(records)

    # Build summary from records if not provided
    summary = dal_response.get("summary") or {}
    if not summary and records:
        total_value = sum(
            float(r.get("VALUE_USD", r.get("trade_value", 0)) or 0)
            for r in records
        )
        summary = {"total_trade_value": total_value, "currency": "USD"}

    # Merge DAL metadata
    metadata = dict(dal_response.get("metadata") or {})
    metadata.pop("scopes", None)
    metadata["intent"] = intent
    metadata["count"] = count

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
    }
