"""Visualization transformers: converting raw DAL rows to Table and Chart JSON formats."""

import re
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.visualization.base import COLUMN_MAP
from app.visualization.numeric_utils import to_float


def _period_sort_key(period_val: Any) -> tuple:
    """Return a (year, month) tuple for chronological sorting of period strings.

    Handles common formats:
      - "2024"        → (2024, 0)
      - "2024-01"     → (2024, 1)
      - "2024-1"      → (2024, 1)
      - "2024/01"     → (2024, 1)
      - "2024M01"     → (2024, 1)   (IMF-style)
      - "202401"      → (2024, 1)   (compact YYYYMM)
      - "20240115"    → (2024, 1)   (compact YYYYMMDD)
    """
    s = str(period_val).strip()
    # YYYY-MM or YYYY/MM
    m = re.match(r'^(\d{4})[-/](\d{1,2})$', s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    # YYYYMnn  (e.g. 2024M01)
    m = re.match(r'^(\d{4})[Mm](\d{1,2})$', s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    # YYYYMMDD (8 digits)
    m = re.match(r'^(\d{4})(\d{2})(\d{2})$', s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    # YYYYMM (6 digits)
    m = re.match(r'^(\d{4})(\d{2})$', s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    # Plain year
    m = re.match(r'^(\d{4})$', s)
    if m:
        return (int(m.group(1)), 0)
    # Fallback: lexicographic
    return (0, 0)


def _humanize_col(col: str) -> str:
    """Convert a snake_case column key into a human-readable Title Case label.

    Examples:
        "period"          -> "Period"
        "partner_country" -> "Partner Country"
        "raw_value"       -> "Raw Value"
        "unit_type"       -> "Unit Type"
    """
    return col.replace("_", " ").title()


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


def transform_to_table(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert raw DAL rows into the standardized table schema with flattened metric fields."""
    if not rows:
        return {"columns": [], "rows": []}

    # Derive column headers and locate the metric key
    first_row = rows[0]
    metric_key = None
    metric_col_name = None
    for k in first_row.keys():
        col = COLUMN_MAP.get(k, k.lower())
        if col.lower() in ("trade_value", "value_usd", "value_khr", "net_weight", "quantity", "growth_rate_pct"):
            metric_key = k
            metric_col_name = col
            break

    columns = []
    seen_cols = set()
    for k in first_row.keys():
        col = COLUMN_MAP.get(k, k.lower())
        if col.lower() in ("frequency", "freq"):
            continue
        if k == metric_key:
            for new_c in ["value", "unit", "scale", "display", "raw_value", "unit_type"]:
                if new_c not in seen_cols:
                    columns.append(_humanize_col(new_c))
                    seen_cols.add(new_c)
        else:
            if col not in seen_cols:
                columns.append(_humanize_col(col))
                seen_cols.add(col)

    transformed_rows = []
    for row in rows:
        t_row = {}
        seen_row = set()
        for k, v in row.items():
            col = COLUMN_MAP.get(k, k.lower())
            if col.lower() in ("frequency", "freq"):
                continue
            if k == metric_key:
                raw_value = None
                value = None
                scale = ""
                unit = ""
                display = ""
                unit_type = ""
                
                if v is not None:
                    try:
                        f_val = float(v)
                        raw_value = f_val
                        abs_val = abs(f_val)
                        
                        # Determine scale and value
                        if metric_col_name.lower() == "growth_rate_pct":
                            scale = ""
                            value = round(f_val, 2)
                        else:
                            if abs_val >= 1000000000:
                                scale = "billion"
                                value = round(f_val / 1000000000, 2)
                            elif abs_val >= 1000000:
                                scale = "million"
                                value = round(f_val / 1000000, 2)
                            else:
                                scale = ""
                                value = round(f_val, 2)
                                
                        # Determine unit
                        if metric_col_name.lower() in ("trade_value", "value_usd"):
                            unit = "USD"
                        elif metric_col_name.lower() == "value_khr":
                            unit = "KHR"
                        elif metric_col_name.lower() in ("net_weight", "quantity"):
                            unit = str(row.get("unit_code", "KG")).upper()
                            if metric_col_name.lower() == "net_weight":
                                unit = "KG"
                        elif metric_col_name.lower() == "growth_rate_pct":
                            unit = "%"
                            
                        # Determine unit_type
                        if unit in ("USD", "KHR"):
                            unit_type = "currency"
                        elif unit in ("KG", "TON"):
                            unit_type = "weight"
                        elif unit == "%":
                            unit_type = "percent"
                        else:
                            unit_type = ""
                            
                        # Determine display
                        if unit == "USD":
                            if scale == "billion":
                                display = f"${value:.2f} billion"
                            elif scale == "million":
                                display = f"${value:.2f} million"
                            else:
                                display = f"${value:,.2f}"
                        elif unit == "KHR":
                            if scale == "billion":
                                display = f"៛{value:.2f} billion"
                            elif scale == "million":
                                display = f"៛{value:.2f} million"
                            else:
                                display = f"៛{value:,.2f}"
                        elif unit in ("KG", "TON"):
                            if scale == "billion":
                                display = f"{value:.2f} billion {unit.lower()}"
                            elif scale == "million":
                                display = f"{value:.2f} million {unit.lower()}"
                            else:
                                display = f"{value:,.2f} {unit.lower()}"
                        elif unit == "%":
                            display = f"{value:+.2f}%"
                        else:
                            if scale == "billion":
                                display = f"{value:.2f} billion"
                            elif scale == "million":
                                display = f"{value:.2f} million"
                            else:
                                display = f"{value:,.2f}"
                                
                    except (ValueError, TypeError):
                        pass
                
                t_row["value"] = value
                t_row["unit"] = unit
                t_row["scale"] = scale
                t_row["display"] = display
                t_row["raw_value"] = raw_value
                t_row["unit_type"] = unit_type
            else:
                if col not in seen_row:
                    # Title-case country name for readability
                    if col == "partner_country" and isinstance(v, str):
                        v = v.title()
                    t_row[col] = v
                    seen_row.add(col)

        transformed_rows.append(t_row)

    # Sort rows chronologically by period when the column is present
    if "period" in columns:
        transformed_rows.sort(key=lambda r: _period_sort_key(r.get("period", "")))

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
    sort_order: str = "desc",
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
            f = _normalize_flow_to_ex_im(r.get(flow_key, "EX"))
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

    # Cap single series while preserving original table/records order
    original_count = len(rows)
    settings = get_settings()
    limit_cap = user_limit if user_limit is not None else settings.max_chart_items
    capped_rows = rows[:limit_cap]

    labels = []
    full_labels = []
    data = []

    has_multiple_flows = False
    if flow_key:
        flows_present = {str(r.get(flow_key)).upper() for r in rows if r.get(flow_key) is not None}
        has_multiple_flows = len(flows_present) >= 2

    for r in capped_rows:
        lbl = r.get(label_col) or "Unknown"
        val = to_float(r.get(value_col))

        lbl_str = str(lbl)
        if str(label_col).upper() == "FLOW":
            lbl_str = FLOW_LABELS.get(_normalize_flow_to_ex_im(lbl_str), lbl_str)
        elif has_multiple_flows and flow_key:
            flow_val = str(r.get(flow_key)).upper()
            lbl_str = f"{lbl_str} ({FLOW_LABELS.get(_normalize_flow_to_ex_im(flow_val), flow_val)})"

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
            val = to_float(r.get(value_col, 0.0))

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
            f = _normalize_flow_to_ex_im(r.get(flow_key, "EX"))
            period = str(r.get(label_col))
            val = to_float(r.get(value_col, 0.0))

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
            val = to_float(r.get(value_col, 0.0))
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

    # Cap single series while preserving original table/records order
    original_count = len(rows)
    settings = get_settings()
    limit_cap = user_limit if user_limit is not None else settings.max_chart_items
    capped_rows = rows[:limit_cap]

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
        val = to_float(r.get(value_col))

        lbl_str = str(lbl)
        if str(label_col).upper() == "FLOW":
            lbl_str = FLOW_LABELS.get(_normalize_flow_to_ex_im(lbl_str), lbl_str)
        elif has_multiple_flows and flow_key:
            flow_val = str(r.get(flow_key)).upper()
            lbl_str = f"{lbl_str} ({FLOW_LABELS.get(_normalize_flow_to_ex_im(flow_val), flow_val)})"

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
