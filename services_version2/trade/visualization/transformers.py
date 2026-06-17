"""Visualization transformers: converting raw DAL rows to Table and Chart JSON formats."""

from typing import Any, Dict, List
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
) -> Dict[str, Any]:
    """Generate chronological multi-series or single-series line chart JSON payload."""
    # Collect all unique periods sorted chronologically
    periods = sorted(list(set(str(r.get(label_col)) for r in rows if r.get(label_col))))

    # Check if we have a FLOW / direction column to split into Export/Import datasets
    has_flow = any("FLOW" in r for r in rows) or any("flow" in r for r in rows)
    flow_key = "FLOW" if any("FLOW" in r for r in rows) else "flow"

    datasets = []
    flow_labels = {"EX": "Exports", "IM": "Imports"}

    if has_flow:
        # Group data by flow code
        flow_groups = {}
        for r in rows:
            f = str(r.get(flow_key, "EX")).upper()
            period = str(r.get(label_col))
            val = r.get(value_col, 0.0)
            try:
                val = float(val) if val is not None else 0.0
            except (ValueError, TypeError):
                val = 0.0

            if f not in flow_groups:
                flow_groups[f] = {}
            flow_groups[f][period] = val

        for flow_code, label_name in flow_labels.items():
            if flow_code in flow_groups or any(flow_code == k for k in flow_groups.keys()):
                # Construct data matching chronological period list
                flow_data = []
                for p in periods:
                    flow_data.append(flow_groups.get(flow_code, {}).get(p, 0.0))
                datasets.append({
                    "label": label_name,
                    "data": flow_data,
                })
    else:
        # Single dataset line chart
        line_data = []
        period_map = {}
        for r in rows:
            period = str(r.get(label_col))
            val = r.get(value_col, 0.0)
            try:
                val = float(val) if val is not None else 0.0
            except (ValueError, TypeError):
                val = 0.0
            period_map[period] = val

        for p in periods:
            line_data.append(period_map.get(p, 0.0))

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
