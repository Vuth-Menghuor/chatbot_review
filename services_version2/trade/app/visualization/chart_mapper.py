"""Visualization mapper: dynamically resolves, formats, and transforms DAL rows to UI targets."""

from typing import Any, Dict, List, Optional

from app.visualization.registry import VISUALIZATION_REGISTRY
from app.visualization.transformers import (
    transform_to_bar_chart,
    transform_to_line_chart,
    transform_to_pie_chart,
    transform_to_table,
)


def _normalize_flow_to_ex_im(flow: str) -> str:
    """Standardize flow strings (e.g. 'EXPORT' or 'EX' -> 'EX', 'IMPORT' or 'IM' -> 'IM')."""
    if not flow:
        return ""
    flow_clean = str(flow).strip().upper()
    if flow_clean in ("EX", "EXPORT"):
        return "EX"
    if flow_clean in ("IM", "IMPORT"):
        return "IM"
    return flow_clean


def _resolve_column_key(row: Dict[str, Any], target_key: str) -> str:
    """Find a matching key in the row, supporting exact and case-insensitive fallbacks."""
    if target_key in row:
        return target_key
    # Check lowercased comparison
    target_lower = target_key.lower()
    for k in row.keys():
        if k.lower() == target_lower:
            return k
    # Default fallbacks if the registered column is missing
    fallback_maps = {
        "PARTNER_COUNTRY": ["partner_country", "HS_CODE", "hs_code", "FLOW", "flow", "PERIOD", "period"],
        "VALUE_USD": ["trade_value", "NET_WEIGHT", "net_weight"],
        "PERIOD": ["period", "FLOW", "flow"],
        "FLOW": ["flow", "PARTNER_COUNTRY", "partner_country"],
        "HS_CODE": ["hs_code", "HS_CHAPTER", "hs_chapter", "HS_HEADING", "hs_heading"],
        "HS_CHAPTER": ["hs_chapter", "HS_CODE", "hs_code", "HS_HEADING", "hs_heading"],
        "HS_HEADING": ["hs_heading", "HS_CODE", "hs_code", "HS_CHAPTER", "hs_chapter"],
        # An empty list forces the catch-all path, which is intercepted by the growth guard below.
        "growth_rate_pct": [],
    }
    for fb in fallback_maps.get(target_key, []):
        for k in row.keys():
            if k == fb or k.lower() == fb.lower():
                return k
    # Return first available key as a absolute fallback
    return list(row.keys())[0] if row else target_key


def _resolve_group_by_column(first_row: Dict[str, Any], group_by: List[str]) -> Optional[str]:
    """Resolve the first usable group_by dimension to an actual key present in the row.

    Shared helper used both for non-trend label-column overrides and for
    trend-intent secondary series resolution. Returns None if no group_by
    dimension can be matched against the row's keys.
    """
    from app.registry.semantic_registry import find_dimension_by_synonym

    for g in group_by:
        mapped_g = find_dimension_by_synonym(str(g)) or str(g)
        if mapped_g in first_row:
            return mapped_g
        if mapped_g.upper() in first_row:
            return mapped_g.upper()
        for k in first_row.keys():
            if k.lower() == mapped_g.lower():
                return k
    return None




def generate_visualizations(
    rows: List[Dict[str, Any]],
    intent: str,
    query_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate both table and graphical visualization payloads for the frontend."""
    if not rows:
        chart_type = "line" if intent == "trend" else ("pie" if intent in ["summary", "breakdown"] else "bar")
        title = f"No Data Found for {intent.replace('_', ' ').capitalize()}"
        return {
            "table": {"columns": [], "rows": []},
            "visualization": {
                "type": chart_type,
                "title": title,
                "labels": [],
                "datasets": []
            }
        }

    params = query_params or {}

    # 1. Transform Table Data (always included)
    table_data = transform_to_table(rows)

    # 2. Get registered configuration for this query intent
    config = VISUALIZATION_REGISTRY.get(intent, VISUALIZATION_REGISTRY["summary"])
    chart_type = config["type"]

    user_pref = params.get("chart_preference") or params.get("extra", {}).get("chart_preference")
    if user_pref in ("bar", "line", "pie", "kpi"):
        chart_type = user_pref

    # Resolve actual keys from rows
    first_row = rows[0]

    group_by = params.get("group_by") or []

    # Check if PERIOD is present in the response rows
    period_key = None
    for k in first_row.keys():
        if k.upper() == "PERIOD":
            period_key = k
            break

    # Check if this query is explicitly for a single period/year
    is_single_period = False
    if params.get("period") and not params.get("start_period") and not params.get("end_period"):
        years_list = params.get("years")
        if not years_list or len(years_list) <= 1:
            is_single_period = True
    elif not params.get("period") and not params.get("start_period") and not params.get("end_period"):
        # No temporal fields? Defaults to a single year
        years_list = params.get("years")
        if not years_list or len(years_list) <= 1:
            is_single_period = True

    is_time_series_comparison = False
    partner_col = next((k for k in first_row.keys() if k.upper() == "PARTNER_COUNTRY"), None)
    if intent == "comparison" and period_key and partner_col:
        freq = params.get("frequency") or ""
        unique_periods = set(str(r.get(period_key)) for r in rows if r.get(period_key) is not None)
        unique_partners = set(str(r.get(partner_col)) for r in rows if r.get(partner_col) is not None)
        if (freq in ("M", "Q", "S") or len(unique_periods) > 1) and len(unique_partners) > 1:
            is_time_series_comparison = True

    # Override default label column if an explicit group_by dimension is present
    # in the parameters. NOTE: for "trend" intent we deliberately do NOT
    # override the label column (it must stay PERIOD so the X-axis remains
    # chronological) — but we DO need to resolve the group_by dimension
    # separately so it can become the *series* split (see series_col below).
    target_label_col = config["label_col"]
    if intent != "trend" and group_by:
        resolved = _resolve_group_by_column(first_row, group_by)
        if resolved:
            target_label_col = resolved

    label_col = _resolve_column_key(first_row, target_label_col)

    if is_time_series_comparison:
        label_col = period_key
    elif intent in ("growth", "comparison", "trend") and not is_single_period and period_key:
        label_col = period_key

    default_value_col = config["value_col"]
    metrics_list = params.get("metrics") or []
    if metrics_list:
        primary_metric = metrics_list[0]
        if "WEIGHT" in str(primary_metric).upper():
            default_value_col = "NET_WEIGHT"
        elif "USD" in str(primary_metric).upper():
            default_value_col = "VALUE_USD"
        elif "KHR" in str(primary_metric).upper():
            default_value_col = "VALUE_KHR"

    value_col = _resolve_column_key(first_row, default_value_col)

    # 1. growth_rate_pct present and non-null in ≥1 row AND growth_valid == True → allow chart
    # 2. Any other condition → empty state only
    # 3. VALUE_USD substitution under growth intent → PROHIBITED (structurally enforced here)
    if intent == "growth":
        # Resolve distinct periods directly from rows to stay self-contained
        period_key_for_growth = None
        for k in first_row.keys():
            if k.upper() == "PERIOD":
                period_key_for_growth = k
                break
        distinct_periods = 0
        if period_key_for_growth:
            distinct_periods = len(set(str(r.get(period_key_for_growth, "")) for r in rows if r.get(period_key_for_growth)))

        growth_valid = distinct_periods >= 2
        has_growth_col = any(
            r.get("growth_rate_pct") is not None for r in rows
        )
        if not growth_valid or not has_growth_col:
            return {
                "table": table_data,
                "visualization": {
                    "type": "empty",
                    "title": "Growth Rate (%) Not Available",
                    "message": (
                        "Insufficient baseline data to render growth chart. "
                        "A prior period is required to compute the growth rate."
                    ),
                    "labels": [],
                    "datasets": [],
                }
            }

    # Dynamic Visual Suitability Overrides
    if not user_pref:
        if intent == "summary":
            test_rows = rows
            requested_flow = params.get("trade_direction") or \
                             params.get("filters", {}).get("FLOW")
            if requested_flow:
                test_rows = [
                    r for r in rows
                    if str(r.get("FLOW", r.get("flow", ""))).upper()
                       == requested_flow.upper()
                ]
            if len(test_rows) <= 1:
                chart_type = "kpi"
            else:
                chart_type = "bar"
        elif intent == "breakdown":
            if str(label_col).upper() in ["MODE_OF_TRANSPORT", "SITC_SECTION", "FLOW"]:
                chart_type = "pie"
            else:
                chart_type = "bar"
        elif intent in ("growth", "comparison"):
            if is_time_series_comparison:
                chart_type = "line"
            elif str(label_col).upper() == "PERIOD":
                if not is_single_period:
                    chart_type = "line"
                else:
                    chart_type = "bar"

    # For line charts, resolve a secondary series column from group_by
    # (e.g. MODE_OF_TRANSPORT or PARTNER_COUNTRY) so transform_to_line_chart can build one
    # line per group instead of a single, silently-overwritten series.
    series_col = None
    if chart_type == "line" and group_by:
        series_col = _resolve_group_by_column(first_row, group_by)
        # Don't treat the period column itself as a series split.
        if series_col and series_col.upper() == str(label_col).upper():
            series_col = None
    if intent == "trend":
        series_col = None
    if is_time_series_comparison:
        series_col = partner_col

    # Use static title directly from registry config
    title = config["title"]
    dataset_label = config.get("dataset_label", "Trade Value (USD)")

    # Resolve target metric labels
    if "net_weight" in value_col.lower() or "weight" in value_col.lower():
        dataset_label = "Net Weight (KG)"

    # Handle aggregation for trade balance queries to prevent duplicate/double label rendering
    chart_rows = list(rows)
    requested_flow = params.get("trade_direction") or \
                     params.get("filters", {}).get("FLOW")
    if requested_flow and intent == "summary":
        req_flow_norm = _normalize_flow_to_ex_im(requested_flow)
        chart_rows = [
            r for r in rows
            if not any(k.upper() == "FLOW" for k in r.keys()) or \
               _normalize_flow_to_ex_im(r.get(next(k for k in r.keys() if k.upper() == "FLOW"), r.get("flow", ""))) == req_flow_norm
        ]

    if intent == "trade_balance":
        flow_key = None
        for k in first_row.keys():
            if k.upper() == "FLOW":
                flow_key = k
                break

        labels_list = [str(r.get(label_col)) for r in rows if r.get(label_col) is not None]
        has_duplicates = len(labels_list) != len(set(labels_list))

        if flow_key and label_col.upper() != flow_key.upper() and has_duplicates:
            aggregated_map = {}
            for r in rows:
                lbl = r.get(label_col)
                if lbl is None:
                    continue
                lbl_str = str(lbl)
                val = r.get(value_col, 0.0)
                try:
                    val = float(val) if val is not None else 0.0
                except (ValueError, TypeError):
                    val = 0.0

                flow_val = str(r.get(flow_key, "")).upper()

                if lbl_str not in aggregated_map:
                    aggregated_map[lbl_str] = dict(r)
                    aggregated_map[lbl_str][value_col] = 0.0

                if flow_val == "EX" or "EXPORT" in flow_val:
                    aggregated_map[lbl_str][value_col] += val
                elif flow_val == "IM" or "IMPORT" in flow_val:
                    aggregated_map[lbl_str][value_col] -= val
                else:
                    aggregated_map[lbl_str][value_col] += val

            seen_labels = []
            new_rows = []
            for r in rows:
                lbl = r.get(label_col)
                if lbl is not None:
                    lbl_str = str(lbl)
                    if lbl_str not in seen_labels:
                        seen_labels.append(lbl_str)
                        new_rows.append(aggregated_map[lbl_str])
            chart_rows = new_rows
            if "net_weight" in value_col.lower() or "weight" in value_col.lower():
                dataset_label = "Net Trade Balance (KG)"
            else:
                dataset_label = "Net Trade Balance (USD)"

    # 2.5 Visual Suitability Check: Fallback to KPI card if 1 or 0 unique X-axis labels/rows (single-period queries only)
    if chart_type in ("line", "bar", "pie") and not user_pref:
        is_single_period = params.get("period") is not None
        unique_labels = set(str(r.get(label_col, "")) for r in chart_rows if r.get(label_col) is not None)
        if intent != "trade_balance" and is_single_period and (len(chart_rows) <= 1 or len(unique_labels) <= 1):
            chart_type = "kpi"

    # 3. Transform to designated chart visualization structure
    user_limit = params.get("extra", {}).get("user_limit") or params.get("limit")
    # Resolve sort column to match the order in records/table
    sort_col = None
    sort_param = params.get("sort") or ""
    if "NET_WEIGHT" in sort_param.upper() or "WEIGHT" in sort_param.upper():
        sort_col = "NET_WEIGHT"
    sort_order = params.get("sort_order", "desc")
    visualization_data = None
    if chart_type == "bar":
        visualization_data = transform_to_bar_chart(
            chart_rows, label_col, value_col, title, dataset_label,
            user_limit=user_limit, sort_col=sort_col, sort_order=sort_order
        )
    elif chart_type == "line":
        split_flow = (intent != "growth")
        if is_time_series_comparison:
            split_flow = False
        visualization_data = transform_to_line_chart(
            chart_rows, label_col, value_col, title, series_col=series_col, dataset_label=dataset_label, split_flow=split_flow
        )
    elif chart_type == "pie":
        visualization_data = transform_to_pie_chart(
            chart_rows, label_col, value_col, title, dataset_label, user_limit=user_limit
        )
    elif chart_type == "kpi":
        single_row = chart_rows[0] if chart_rows else {}
        lbl = single_row.get(label_col) or "Value"

        FLOW_LABELS = {"EX": "Exports", "IM": "Imports"}
        lbl_str = str(lbl)
        if str(label_col).upper() == "FLOW":
            lbl_str = FLOW_LABELS.get(_normalize_flow_to_ex_im(lbl_str), lbl_str)

        # Extract requested metrics
        req_metrics = [str(m).upper() for m in (params.get("metrics") or [])]
        has_usd = any("USD" in m or "KHR" in m for m in req_metrics) or not req_metrics
        has_weight = any("WEIGHT" in m for m in req_metrics) or not req_metrics

        usd_col = next((k for k in single_row.keys() if k.upper() in ("VALUE_USD", "VALUE_USD_NET", "TRADE_VALUE")), None)
        weight_col = next((k for k in single_row.keys() if k.upper() in ("NET_WEIGHT", "WEIGHT_KG", "NET_WEIGHT_KG")), None)

        val_usd = 0.0
        if usd_col:
            try:
                val_usd = float(single_row.get(usd_col) or 0.0)
            except (ValueError, TypeError):
                pass

        val_weight = 0.0
        if weight_col:
            try:
                val_weight = float(single_row.get(weight_col) or 0.0)
            except (ValueError, TypeError):
                pass

        unit = "USD"
        val = val_usd
        if not has_usd and has_weight:
            unit = "KG"
            val = val_weight

        # Extract growth rate if present in records
        change_val = None
        for k in single_row.keys():
            if k.lower() in ("growth_rate_pct", "change", "growth_rate"):
                try:
                    change_val = float(single_row[k])
                    break
                except (ValueError, TypeError):
                    pass

        visualization_data = {
            "type": "kpi",
            "title": title,
            "value": val,
            "label": lbl_str,
            "unit": unit,
            "change": change_val,
            "datasets": [{"label": dataset_label, "data": [val]}],
            "labels": [lbl_str]
        }

        if has_usd and has_weight:
            visualization_data["weight"] = val_weight
            visualization_data["weight_unit"] = "KG"
            visualization_data["weight_change"] = None

    return {
        "table": table_data,
        "visualization": visualization_data,
    }
