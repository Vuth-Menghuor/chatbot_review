"""Visualization mapper: dynamically resolves, formats, and transforms DAL rows to UI targets."""

from typing import Any, Dict, List, Optional
from .registry import VISUALIZATION_REGISTRY
from .transformers import (
    transform_to_table,
    transform_to_bar_chart,
    transform_to_line_chart,
    transform_to_pie_chart,
)


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
    from ..core.semantic_registry import find_dimension_by_synonym

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


def _build_dynamic_title(intent: str, config_title: str, query_params: Dict[str, Any], label_col: str = "") -> str:
    """Build a contextual, human-friendly title based on query filters and intent."""
    from ..core.nlg.formatters import COUNTRY_NAMES

    # 1. Resolve flow (Export / Import / Trade)
    raw_flow = query_params.get("flow") or query_params.get("trade_direction") or "trade"
    if str(raw_flow).upper() in ("EX", "EXPORT"):
        flow = "Export"
    elif str(raw_flow).upper() in ("IM", "IMPORT"):
        flow = "Import"
    else:
        flow = str(raw_flow).capitalize()

    # 2. Resolve year
    year = query_params.get("year") or query_params.get("period") or ""

    # 3. Resolve partner
    partner = query_params.get("partner") or query_params.get("partner_country") or ""
    # Support list of partner countries (like in comparison/ranking)
    if not partner:
        partners_list = query_params.get("partner_countries")
        if isinstance(partners_list, list) and len(partners_list) == 1:
            partner = partners_list[0]
            
    if partner and len(str(partner)) == 2:
        partner = COUNTRY_NAMES.get(str(partner).upper(), partner)

    # 4. Construct scope
    scope = f" with {partner}" if partner else ""
    if year:
        scope += f" in {year}"

    # 5. Templates mapping
    templates = {
        "summary": f"{flow} Summary{scope}",
        "ranking": f"Top {flow} Partners{scope}",
        "trend": f"{flow} Trend Over Time{scope}",
        "comparison": f"{flow} Comparison{scope}",
        "breakdown": f"{flow} Breakdown by Product{scope}",
        "growth": f"{flow} Growth Rate{scope}",
        "trade_balance": f"Trade Balance Summary{scope}"
    }

    # For ranking, check sorting order to see if it's "Bottom"
    if intent == "ranking":
        sort_order = query_params.get("sort_order") or ""
        prefix = "Bottom" if "asc" in str(sort_order).lower() else "Top"
        templates["ranking"] = f"{prefix} {flow} Partners{scope}"

    title = templates.get(intent, f"{flow} Analysis{scope}")
    return title


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

    # Resolve actual keys from rows
    first_row = rows[0]

    group_by = params.get("group_by") or []

    # Override default label column if an explicit group_by dimension is present
    # in the parameters. NOTE: for "trend" intent we deliberately do NOT
    # override the label column (it must stay PERIOD so the X-axis remains
    # chronological) — but we DO need to resolve the group_by dimension
    # separately so it can become the *series* split (see series_col below).
    # Previously this block was skipped entirely for intent == "trend",
    # which meant a group_by like MODE_OF_TRANSPORT was silently dropped
    # for trend charts, causing all groups to collapse into a single
    # (incorrectly overwritten) line.
    target_label_col = config["label_col"]
    if intent != "trend" and group_by:
        resolved = _resolve_group_by_column(first_row, group_by)
        if resolved:
            target_label_col = resolved

    label_col = _resolve_column_key(first_row, target_label_col)
    value_col = _resolve_column_key(first_row, config["value_col"])

    # For trend intent, resolve a secondary series column from group_by
    # (e.g. MODE_OF_TRANSPORT) so transform_to_line_chart can build one
    # line per group instead of a single, silently-overwritten series.
    series_col = None
    if intent == "trend" and group_by:
        series_col = _resolve_group_by_column(first_row, group_by)
        # Don't treat the period column itself as a series split.
        if series_col and series_col.upper() == str(label_col).upper():
            series_col = None

    # Build dynamic contextual title
    title = _build_dynamic_title(intent, config["title"], params, label_col)
    dataset_label = config.get("dataset_label", "Trade Value (USD)")

    # Resolve target metric labels
    if "net_weight" in value_col.lower() or "weight" in value_col.lower():
        dataset_label = "Net Weight (KG)"

    # Handle aggregation for trade balance queries to prevent duplicate/double label rendering
    chart_rows = list(rows)
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

    # 3. Transform to designated chart visualization structure
    visualization_data = None
    if chart_type == "bar":
        visualization_data = transform_to_bar_chart(
            chart_rows, label_col, value_col, title, dataset_label
        )
    elif chart_type == "line":
        visualization_data = transform_to_line_chart(
            chart_rows, label_col, value_col, title, series_col=series_col
        )
    elif chart_type == "pie":
        visualization_data = transform_to_pie_chart(
            chart_rows, label_col, value_col, title, dataset_label
        )

    return {
        "table": table_data,
        "visualization": visualization_data,
    }