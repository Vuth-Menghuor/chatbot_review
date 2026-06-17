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


def _build_dynamic_title(intent: str, config_title: str, query_params: Dict[str, Any], label_col: str = "") -> str:
    """Build a contextual, human-friendly title based on query filters and intent."""
    flow = query_params.get("trade_direction")
    flow_text = ""
    if flow == "EX":
        flow_text = "Export "
    elif flow == "IM":
        flow_text = "Import "

    year = query_params.get("year")
    year_text = f" in {year}" if year else ""

    # Determine the entity type being ranked/compared
    entity_text = "Partners"
    if label_col:
        label_lower = label_col.lower()
        if "hs_" in label_lower or "chapter" in label_lower or "heading" in label_lower or "code" in label_lower or "product" in label_lower:
            entity_text = "Products"
        elif "transport" in label_lower or "mode" in label_lower:
            entity_text = "Transport Modes"

    # Adjust default title to be specific
    title = config_title
    if intent == "ranking":
        sort_order = query_params.get("sort_order") or ""
        prefix = "Bottom" if "asc" in str(sort_order).lower() else "Top"
        title = f"{prefix} {flow_text}{entity_text}{year_text}"
    elif intent == "trend":
        title = f"{flow_text}Trade Trend over Time{year_text}"
    elif intent == "comparison":
        title = f"{flow_text}Trade Comparison{year_text}"
    elif intent == "breakdown":
        title = f"{flow_text}Trade Breakdown by Product{year_text}"
    elif intent == "growth":
        title = f"{flow_text}Trade Growth{year_text}"
    elif intent == "trade_balance":
        title = f"Trade Balance Summary{year_text}"
    else:
        title = f"{flow_text}{title}{year_text}"

    return title


def generate_visualizations(
    rows: List[Dict[str, Any]],
    intent: str,
    query_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate both table and graphical visualization payloads for the frontend."""
    if not rows:
        return {"table": {"columns": [], "rows": []}, "visualization": None}

    params = query_params or {}

    # 1. Transform Table Data (always included)
    table_data = transform_to_table(rows)

    # 2. Get registered configuration for this query intent
    config = VISUALIZATION_REGISTRY.get(intent, VISUALIZATION_REGISTRY["summary"])
    chart_type = config["type"]

    # Resolve actual keys from rows
    first_row = rows[0]

    # Override default label column if an explicit group_by dimension is present in the parameters
    target_label_col = config["label_col"]
    if params.get("group_by"):
        for g in params["group_by"]:
            from ..core.semantic_registry import find_dimension_by_synonym
            mapped_g = find_dimension_by_synonym(str(g)) or str(g)
            # Resolve to upper or original key casing
            if mapped_g in first_row:
                target_label_col = mapped_g
                break
            elif mapped_g.upper() in first_row:
                target_label_col = mapped_g.upper()
                break
            else:
                matched = False
                for k in first_row.keys():
                    if k.lower() == mapped_g.lower():
                        target_label_col = k
                        matched = True
                        break
                if matched:
                    break

    label_col = _resolve_column_key(first_row, target_label_col)
    value_col = _resolve_column_key(first_row, config["value_col"])

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
            chart_rows, label_col, value_col, title
        )
    elif chart_type == "pie":
        visualization_data = transform_to_pie_chart(
            chart_rows, label_col, value_col, title, dataset_label
        )

    return {
        "table": table_data,
        "visualization": visualization_data,
    }
