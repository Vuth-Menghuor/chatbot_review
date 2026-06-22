"""Visualization transformers: converting raw DAL rows to Table and Chart JSON formats."""

from typing import Any, Dict, List, Optional
from .base import COLUMN_MAP


def transform_to_table(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert raw DAL rows into the standardized table schema."""
    if not rows:
        return {"columns": [], "rows": []}

    # Derive column headers from the keys of the first row
    first_row = rows[0]
    columns = [COLUMN_MAP.get(k, k.lower()) for k in first_row.keys()]

    transformed_rows = []
    for row in rows:
        t_row = {}
        for k, v in row.items():
            t_key = COLUMN_MAP.get(k, k.lower())
            t_row[t_key] = v
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
) -> Dict[str, Any]:
    """Generate bar chart JSON payload."""
    labels = []
    data = []

    for r in rows:
        lbl = r.get(label_col) or "Unknown"
        val = r.get(value_col, 0.0)
        try:
            val = float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            val = 0.0
        labels.append(str(lbl))
        data.append(val)

    return {
        "type": "bar",
        "title": title,
        "labels": labels,
        "datasets": [
            {
                "label": dataset_label,
                "data": data,
            }
        ],
    }


def transform_to_line_chart(
    rows: List[Dict[str, Any]],
    label_col: str,
    value_col: str,
    title: str,
    series_col: Optional[str] = None,
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

    if has_flow:
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
            "label": "Trade Value (USD)",
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
) -> Dict[str, Any]:
    """Generate pie chart JSON payload."""
    labels = []
    data = []

    for r in rows:
        lbl = r.get(label_col) or "Other"
        val = r.get(value_col, 0.0)
        try:
            val = float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            val = 0.0
        labels.append(str(lbl))
        data.append(val)

    return {
        "type": "pie",
        "title": title,
        "labels": labels,
        "datasets": [
            {
                "label": dataset_label,
                "data": data,
            }
        ],
    }