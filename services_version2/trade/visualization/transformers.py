"""Visualization transformers: converting raw DAL rows to Table and Chart JSON formats."""

from typing import Any, Dict, List, Optional
from visualization.base import COLUMN_MAP
from config import get_settings


def transform_to_table(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert raw DAL rows into the standardized table schema."""
    if not rows:
        return {"columns": [], "rows": []}

    # Derive column headers from the keys of the first row
    first_row = rows[0]
    columns = []
    seen_cols = set()
    for k in first_row.keys():
        col = COLUMN_MAP.get(k, k.lower())
        if col not in seen_cols:
            columns.append(col)
            seen_cols.add(col)

    transformed_rows = []
    for row in rows:
        t_row = {}
        seen_row = set()
        for k, v in row.items():
            t_key = COLUMN_MAP.get(k, k.lower())
            if t_key not in seen_row:
                t_row[t_key] = v
                seen_row.add(t_key)
            # If duplicate key maps to same canonical name, keep first value
        transformed_rows.append(t_row)

    return {
        "columns": columns,
        "rows": transformed_rows,
    }


def transform_to_bar_chart(
    rows: List[Dict[str, Any]],
    label_col: str,
    value_col: str,
    title: str,
    dataset_label: str = "Trade Value (USD)",
    user_limit: Optional[int] = None,
    sort_col: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate bar chart JSON payload."""
    if not rows:
        return {"type": "bar", "title": title, "labels": [], "datasets": []}

    flow_key = "FLOW" if any("FLOW" in r for r in rows) else "flow" if any("flow" in r for r in rows) else None
    period_key = "PERIOD" if any("PERIOD" in r for r in rows) else "period" if any("period" in r for r in rows) else None
    
    # Detect multi-period + multi-flow
    flows_set = {str(r.get(flow_key)).upper() for r in rows if flow_key and r.get(flow_key) is not None}
    periods_set = {str(r.get(period_key)) for r in rows if period_key and r.get(period_key) is not None}
    
    if flow_key and period_key and len(flows_set) >= 2 and len(periods_set) >= 2:
        # Grouped bar chart (one dataset per flow, periods as labels)
        periods = sorted(list(periods_set))
        flow_groups: Dict[str, Dict[str, float]] = {}
        for r in rows:
            f = str(r.get(flow_key, "EX")).upper()
            p = str(r.get(period_key))
            val = 0.0
            try:
                val = float(r.get(value_col, 0.0))
            except (ValueError, TypeError):
                pass
            if f not in flow_groups:
                flow_groups[f] = {}
            flow_groups[f][p] = flow_groups[f].get(p, 0.0) + val
            
        datasets = []
        flow_labels = {"EX": "Exports", "IM": "Imports"}
        for flow_code, label_name in flow_labels.items():
            if flow_code in flow_groups:
                data = [flow_groups[flow_code].get(p, 0.0) for p in periods]
                datasets.append({
                    "label": label_name,
                    "data": data,
                })
        
        # Sort and cap periods to limit_cap
        settings = get_settings()
        limit_cap = user_limit if user_limit is not None else settings.max_chart_items
        original_count = len(periods)
        if original_count > limit_cap:
            period_sums = {}
            for p in periods:
                period_sums[p] = sum(flow_groups[f].get(p, 0.0) for f in flow_groups)
            sorted_periods = sorted(periods, key=lambda p: period_sums[p], reverse=True)[:limit_cap]
            sorted_periods.sort()
            
            capped_datasets = []
            for ds in datasets:
                flow_code = "EX" if ds["label"] == "Exports" else "IM"
                capped_data = [flow_groups[flow_code].get(p, 0.0) for p in sorted_periods]
                capped_datasets.append({
                    "label": ds["label"],
                    "data": capped_data,
                })
            
            return {
                "type": "bar",
                "title": title,
                "labels": sorted_periods,
                "full_labels": sorted_periods,
                "datasets": capped_datasets,
                "note": f"Showing top {limit_cap} of {original_count} results"
            }
        
        return {
            "type": "bar",
            "title": title,
            "labels": periods,
            "full_labels": periods,
            "datasets": datasets,
        }

    FLOW_LABELS = {"EX": "Exports", "IM": "Imports"}
    
    # Sort and cap single series
    original_count = len(rows)
    sorted_rows = list(rows)
    
    def _to_float(v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0
            
    effective_sort_col = sort_col if sort_col else value_col
    sorted_rows.sort(key=lambda r: _to_float(r.get(effective_sort_col) or r.get(effective_sort_col.lower())), reverse=True)
    settings = get_settings()
    limit_cap = user_limit if user_limit is not None else settings.max_chart_items
    capped_rows = sorted_rows[:limit_cap]
    
    labels = []
    full_labels = []
    data = []
    
    has_multiple_flows = False
    if flow_key:
        flows_present = {str(r.get(flow_key)).upper() for r in rows if r.get(flow_key) is not None}
        has_multiple_flows = len(flows_present) >= 2

    for r in capped_rows:
        lbl = r.get(label_col) or "Unknown"
        val = _to_float(r.get(value_col))
        
        lbl_str = str(lbl)
        if str(label_col).upper() == "FLOW":
            lbl_str = FLOW_LABELS.get(lbl_str.upper(), lbl_str)
        elif has_multiple_flows:
            flow_val = str(r.get(flow_key)).upper()
            lbl_str = f"{lbl_str} ({FLOW_LABELS.get(flow_val, flow_val)})"
            
        full_labels.append(lbl_str)
        display_lbl = lbl_str
        if len(display_lbl) > 60:
            display_lbl = display_lbl[:57] + "..."
        labels.append(display_lbl)
        data.append(val)
        
    viz_payload = {
        "type": "bar",
        "title": title,
        "labels": labels,
        "full_labels": full_labels,
        "datasets": [
            {
                "label": dataset_label,
                "data": data,
            }
        ],
    }
    if original_count > limit_cap:
        viz_payload["note"] = f"Showing top {limit_cap} of {original_count} results"
        
    return viz_payload


def transform_to_line_chart(
    rows: List[Dict[str, Any]],
    label_col: str,
    value_col: str,
    title: str,
    series_col: Optional[str] = None,
    dataset_label: str = "Trade Value (USD)",
    split_flow: bool = True,
) -> Dict[str, Any]:
    """Generate chronological multi-series or single-series line chart JSON payload.

    Args:
        rows: Raw DAL rows.
        label_col: Column used for the X-axis (chronological periods).
        value_col: Column used for the Y-axis values.
        title: Chart title.
        series_col: Optional column name. When provided (and not the same as
            label_col), each distinct value in this column becomes its own
            line series (e.g. "MODE_OF_TRANSPORT" -> one line per mode).
            This generalizes the previous FLOW-only splitting logic to any
            grouping dimension, fixing the bug where rows sharing the same
            period but differing only in a secondary dimension (like
            transport mode) silently overwrote each other, leaving only the
            last-processed group's data in the chart.
    """
    # Collect all unique periods sorted chronologically
    periods = sorted(list(set(str(r.get(label_col)) for r in rows if r.get(label_col) is not None)))

    def _to_float(v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    # --- General-purpose grouped series (e.g. MODE_OF_TRANSPORT, any group_by dim) ---
    # Takes priority over the legacy FLOW-specific logic below, since it is a
    # strict superset: FLOW is just one possible series_col value.
    if series_col and series_col != label_col and any(series_col in r for r in rows):
        series_groups: Dict[str, Dict[str, float]] = {}
        series_order: List[str] = []  # preserve first-seen order for stable dataset ordering

        for r in rows:
            series_val = r.get(series_col)
            if series_val is None:
                continue
            series_key = str(series_val)
            period = str(r.get(label_col))
            val = _to_float(r.get(value_col, 0.0))

            if series_key not in series_groups:
                series_groups[series_key] = {}
                series_order.append(series_key)
            # Sum in case multiple rows share the same (series, period) pair
            series_groups[series_key][period] = series_groups[series_key].get(period, 0.0) + val

        datasets = []
        for series_key in series_order:
            period_map = series_groups[series_key]
            data = [period_map.get(p, 0.0) for p in periods]
            datasets.append({
                "label": series_key,
                "data": data,
            })

        return {
            "type": "line",
            "title": title,
            "labels": periods,
            "datasets": datasets,
        }

    # --- Legacy FLOW-specific splitting (Exports vs Imports) ---
    has_flow = any("FLOW" in r for r in rows) or any("flow" in r for r in rows)
    flow_key = "FLOW" if any("FLOW" in r for r in rows) else "flow"

    datasets = []
    flow_labels = {"EX": "Exports", "IM": "Imports"}

    if has_flow and split_flow:
        flow_groups: Dict[str, Dict[str, float]] = {}
        for r in rows:
            f = str(r.get(flow_key, "EX")).upper()
            period = str(r.get(label_col))
            val = _to_float(r.get(value_col, 0.0))

            if f not in flow_groups:
                flow_groups[f] = {}
            flow_groups[f][period] = flow_groups[f].get(period, 0.0) + val

        for flow_code, label_name in flow_labels.items():
            if flow_code in flow_groups:
                flow_data = [flow_groups.get(flow_code, {}).get(p, 0.0) for p in periods]
                datasets.append({
                    "label": label_name,
                    "data": flow_data,
                })
    else:
        # Single dataset line chart — only safe to use period_map as a
        # straight overwrite here because there is exactly one row per
        # period in this branch (no secondary grouping dimension present).
        period_map: Dict[str, float] = {}
        for r in rows:
            period = str(r.get(label_col))
            val = _to_float(r.get(value_col, 0.0))
            period_map[period] = period_map.get(period, 0.0) + val

        line_data = [period_map.get(p, 0.0) for p in periods]

        datasets.append({
            "label": dataset_label,
            "data": line_data,
        })

    return {
        "type": "line",
        "title": title,
        "labels": periods,
        "datasets": datasets,
    }


def transform_to_pie_chart(
    rows: List[Dict[str, Any]],
    label_col: str,
    value_col: str,
    title: str,
    dataset_label: str = "Market Share",
    user_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate pie chart JSON payload."""
    FLOW_LABELS = {"EX": "Exports", "IM": "Imports"}
    
    # Sort and cap
    original_count = len(rows)
    sorted_rows = list(rows)
    
    def _to_float(v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0
            
    sorted_rows.sort(key=lambda r: _to_float(r.get(value_col)), reverse=True)
    settings = get_settings()
    limit_cap = user_limit if user_limit is not None else settings.max_chart_items
    capped_rows = sorted_rows[:limit_cap]
    
    labels = []
    full_labels = []
    data = []
    
    flow_key = "FLOW" if any("FLOW" in r for r in rows) else "flow" if any("flow" in r for r in rows) else None
    has_multiple_flows = False
    if flow_key:
        flows_present = {str(r.get(flow_key)).upper() for r in rows if r.get(flow_key) is not None}
        has_multiple_flows = len(flows_present) >= 2

    for r in capped_rows:
        lbl = r.get(label_col) or "Other"
        val = _to_float(r.get(value_col))
        
        lbl_str = str(lbl)
        if str(label_col).upper() == "FLOW":
            lbl_str = FLOW_LABELS.get(lbl_str.upper(), lbl_str)
        elif has_multiple_flows:
            flow_val = str(r.get(flow_key)).upper()
            lbl_str = f"{lbl_str} ({FLOW_LABELS.get(flow_val, flow_val)})"
            
        full_labels.append(lbl_str)
        display_lbl = lbl_str
        if len(display_lbl) > 60:
            display_lbl = display_lbl[:57] + "..."
        labels.append(display_lbl)
        data.append(val)
        
    viz_payload = {
        "type": "pie",
        "title": title,
        "labels": labels,
        "full_labels": full_labels,
        "datasets": [
            {
                "label": dataset_label,
                "data": data,
            }
        ],
    }
    if original_count > limit_cap:
        viz_payload["note"] = f"Showing top {limit_cap} of {original_count} results"
        
    return viz_payload