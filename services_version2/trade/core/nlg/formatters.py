from typing import Any, Dict
from core.countries import CODE_TO_COUNTRY_NAME as COUNTRY_NAMES
from core.transport_modes import TRANSPORT_MODE_LABELS

TRANSPORT_NAMES = TRANSPORT_MODE_LABELS

GROUPABLE_DIMENSIONS = {
    "MODE_OF_TRANSPORT": "mode",
    "PARTNER_COUNTRY": "country",
    "HS_CHAPTER": "hs_chapter",
    "HS_HEADING": "hs_heading",
    "SITC_SECTION": "sitc_section",
    "SITC_DIVISION": "sitc_division",
}


def _resolve_group_label(dim: str, raw_value: Any) -> Any:
    """Resolve a raw dimension value (e.g. country code) to a display label."""
    if raw_value is None:
        return None
    if dim == "PARTNER_COUNTRY":
        return COUNTRY_NAMES.get(str(raw_value).upper(), raw_value)
    if dim == "MODE_OF_TRANSPORT":
        as_code = TRANSPORT_NAMES.get(str(raw_value))
        return as_code if as_code else raw_value
    return raw_value


def extract_facts(payload: Dict[str, Any], query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and format raw query facts from payload and query parameters."""
    intent = query_params.get("intent", "summary")

    # 1. Total trade values
    records = payload.get("records") or []
    
    requested_flow = query_params.get("trade_direction") or \
                     query_params.get("filters", {}).get("FLOW")
    if requested_flow:
        records = [
            r for r in records 
            if not any(k.upper() == "FLOW" for k in r.keys()) or \
               str(r.get(next(k for k in r.keys() if k.upper() == "FLOW"), "")).upper() == requested_flow.upper()
        ]

    # Calculate sum of returned records (subset total)
    subset_trade_value = sum(float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0) for r in records)
    subset_weight = sum(float(r.get("NET_WEIGHT", r.get("net_weight", 0.0)) or 0.0) for r in records)

    summary = payload.get("summary") or {}
    total_trade_value = summary.get("total_trade_value") or payload.get("total_trade_value") or 0.0

    is_global_total = bool(summary.get("total_trade_value") or payload.get("total_trade_value"))
    if (not total_trade_value or intent == "summary") and records:
        total_trade_value = subset_trade_value
        is_global_total = True

    total_weight = 0.0
    summary_weight = summary.get("total_weight_kg")
    if summary_weight is not None:
        total_weight = float(summary_weight)
    elif is_global_total:
        total_weight = sum(float(r.get("NET_WEIGHT", r.get("net_weight", 0.0)) or 0.0) for r in records)

    # 2. Dimensions from filters or parameters
    filters = query_params.get("filters") or {}

    # Flow direction
    flow_raw = filters.get("FLOW") or query_params.get("trade_direction")
    flow = "export" if flow_raw == "EX" else "import" if flow_raw == "IM" else None

    # Partner country
    partner_raw = filters.get("PARTNER_COUNTRY") or query_params.get("partner_country")
    if isinstance(partner_raw, list) and len(partner_raw) == 1:
        partner_raw = partner_raw[0]

    partner_country = None
    if isinstance(partner_raw, str):
        partner_country = COUNTRY_NAMES.get(partner_raw.upper(), partner_raw)
    elif isinstance(partner_raw, list):
        partner_country = [COUNTRY_NAMES.get(c.upper(), c) for c in partner_raw]

    transport_raw = filters.get("MODE_OF_TRANSPORT") or query_params.get("mode_of_transport")
    if isinstance(transport_raw, list) and len(transport_raw) == 1:
        transport_raw = transport_raw[0]
        
    mode_of_transport = None
    if isinstance(transport_raw, (str, int)):
        mode_of_transport = TRANSPORT_NAMES.get(str(transport_raw), str(transport_raw))
    elif isinstance(transport_raw, list):
        mode_of_transport = [TRANSPORT_NAMES.get(str(t), str(t)) for t in transport_raw]

    # Period
    period = query_params.get("period")
    start_period = query_params.get("start_period")
    end_period = query_params.get("end_period")

    time_context = period
    if not time_context:
        if start_period and end_period:
            if start_period == end_period:
                time_context = start_period
            else:
                time_context = f"from {start_period} to {end_period}"
        elif start_period:
            time_context = f"since {start_period}"
        elif end_period:
            time_context = f"until {end_period}"

    sort_raw = query_params.get("sort")
    sort_order = query_params.get("sort_order")
    if not sort_order and isinstance(sort_raw, str) and ":" in sort_raw:
        sort_order = sort_raw.split(":")[-1]
    if not sort_order:
        sort_order = "desc"

    # Intent specific facts
    facts = {
        "intent": intent,
        "flow": flow,
        "partner_country": partner_country,
        "mode_of_transport": mode_of_transport,
        "period": time_context,
        "total_trade_value_usd": float(total_trade_value) if is_global_total else None,
        "total_weight_kg": float(total_weight) if is_global_total else None,
        "subset_trade_value_usd": float(subset_trade_value),
        "subset_weight_kg": float(subset_weight),
        "sort_order": sort_order,
        "limit": query_params.get("limit"),
        "metrics": query_params.get("metrics") or ["VALUE_USD"],
    }

    # Add product code context
    hs_code = filters.get("HS_CODE") or filters.get("HS_HEADING") or query_params.get("hs_code")
    hs_chapter = filters.get("HS_CHAPTER") or query_params.get("hs_chapter")
    sitc_section = filters.get("SITC_SECTION") or query_params.get("sitc_section")
    sitc_division = filters.get("SITC_DIVISION") or query_params.get("sitc_division")
    
    if hs_code:
        facts["hs_code"] = hs_code
    elif hs_chapter:
        facts["hs_chapter"] = hs_chapter

    if sitc_section:
        facts["sitc_section"] = sitc_section
    if sitc_division:
        facts["sitc_division"] = sitc_division

    group_by = query_params.get("group_by") or query_params.get("dimensions") or []
    grouped_dim = next((dim for dim in group_by if dim in GROUPABLE_DIMENSIONS), None)

    if grouped_dim and records and intent != "comparison":
        breakdown: Dict[str, Dict[str, float]] = {}
        for r in records:
            raw_val = r.get(grouped_dim)
            label = _resolve_group_label(grouped_dim, raw_val)
            if label is None:
                continue
            label = str(label)
            entry = breakdown.setdefault(label, {"trade_value_usd": 0.0, "weight_kg": 0.0})
            entry["trade_value_usd"] += float(r.get("VALUE_USD", 0.0) or 0.0)
            entry["weight_kg"] += float(r.get("NET_WEIGHT", 0.0) or 0.0)

        breakdown_records = [
            {"label": label, "trade_value_usd": vals["trade_value_usd"], "weight_kg": vals["weight_kg"]}
            for label, vals in breakdown.items()
        ]
        # Sort descending by value so the largest group leads the summary.
        breakdown_records.sort(key=lambda x: x["trade_value_usd"], reverse=True)

        facts["grouped_by"] = GROUPABLE_DIMENSIONS[grouped_dim]
        facts["group_breakdown_records"] = breakdown_records

        if grouped_dim == "MODE_OF_TRANSPORT":
            facts["mode_breakdown_records"] = breakdown_records

    # If comparison, list all country trade values
    if intent == "comparison" and records:
        country_comparison = []
        for r in records:
            country_code = r.get("PARTNER_COUNTRY")
            country_name = COUNTRY_NAMES.get(str(country_code).upper(), country_code) if country_code else "Unknown"
            val = float(r.get("VALUE_USD", 0.0))
            weight = float(r.get("NET_WEIGHT", 0.0))
            period_val = r.get("PERIOD") or r.get("period")
            country_comparison.append({"country": country_name, "trade_value_usd": val, "weight_kg": weight, "period": period_val})
        facts["comparison_records"] = country_comparison

    # If ranking, list top records
    elif intent == "ranking" and records:
        top_records = []
        ranked_dimension = "PARTNER_COUNTRY"
        for r in records:
            lbl_key = "PARTNER_COUNTRY"
            if "HS_CHAPTER" in r:
                lbl_key = "HS_CHAPTER"
                ranked_dimension = "HS_CHAPTER"
            elif "HS_HEADING" in r:
                lbl_key = "HS_HEADING"
                ranked_dimension = "HS_HEADING"
            elif "MODE_OF_TRANSPORT" in r:
                lbl_key = "MODE_OF_TRANSPORT"
                ranked_dimension = "MODE_OF_TRANSPORT"

            lbl_val = r.get(lbl_key)
            if lbl_key == "PARTNER_COUNTRY" and lbl_val:
                lbl_val = COUNTRY_NAMES.get(str(lbl_val).upper(), lbl_val)
            elif lbl_key == "MODE_OF_TRANSPORT" and lbl_val:
                lbl_val = TRANSPORT_NAMES.get(str(lbl_val), lbl_val)

            val = float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0)
            weight = float(r.get("NET_WEIGHT", r.get("net_weight", 0.0)) or 0.0)
            top_records.append({"label": lbl_val, "trade_value_usd": val, "weight_kg": weight})
        facts["ranking_records"] = top_records
        facts["ranked_dimension"] = ranked_dimension

    # If growth, compute and attach rates
    elif intent == "growth" and records:
        growth_records = []
        for r in records:
            p = r.get("PERIOD") or r.get("period")
            val = float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0)
            weight = float(r.get("NET_WEIGHT", r.get("net_weight", 0.0)) or 0.0)
            g_rate_raw = r.get("growth_rate_pct")
            growth_rate = float(g_rate_raw) if g_rate_raw is not None else None
            
            rec = {
                "period": p,
                "trade_value_usd": val,
                "growth_rate_pct": growth_rate,
                "weight_kg": weight
            }
            for k, v in r.items():
                if k.upper() not in ("PERIOD", "FREQ", "VALUE_USD", "NET_WEIGHT", "VALUE_KHR", "GROWTH_RATE_PCT"):
                    if k.upper() == "PARTNER_COUNTRY" and v:
                        v = COUNTRY_NAMES.get(str(v).upper(), v)
                    rec[k] = v
            growth_records.append(rec)
        facts["growth_records"] = growth_records

    # If trend, list chronological values
    elif intent == "trend" and records:
        trend_records = []
        for r in records:
            p = r.get("PERIOD") or r.get("period")
            val = float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0)
            weight = float(r.get("NET_WEIGHT", r.get("net_weight", 0.0)) or 0.0)
            trend_records.append({"period": p, "trade_value_usd": val, "weight_kg": weight})
        # Sort chronologically
        trend_records.sort(key=lambda x: str(x["period"]))
        facts["trend_records"] = trend_records

    # If trade_balance, list all records and pre-calculate period-by-period balances
    elif intent == "trade_balance" and records:
        tb_records = []
        period_data = {}
        for r in records:
            p = r.get("PERIOD") or r.get("period")
            flow = r.get("FLOW") or r.get("flow")
            val = float(r.get("VALUE_USD", r.get("value_usd", r.get("trade_value", 0.0))) or 0.0)
            tb_records.append({"period": p, "flow": flow, "value_usd": val})
            
            entry = period_data.setdefault(p, {"EX": 0.0, "IM": 0.0})
            flow_type = "EX" if str(flow).upper() == "EX" else "IM"
            entry[flow_type] += val
            
        facts["trade_balance_records"] = tb_records
        
        # Pre-calculate period balances so LLM can read and state them directly (Fix #8)
        period_balances = []
        for p, data in sorted(period_data.items()):
            ex = data["EX"]
            im = data["IM"]
            bal = ex - im
            status = "surplus" if bal >= 0 else "deficit"
            
            # Simple format inline
            abs_bal = abs(bal)
            if abs_bal >= 1e9:
                bal_f = f"${abs_bal / 1e9:.2f} billion"
            elif abs_bal >= 1e6:
                bal_f = f"${abs_bal / 1e6:.2f} million"
            else:
                bal_f = f"${abs_bal:,.2f}"
                
            period_balances.append({
                "period": p,
                "exports_usd": ex,
                "imports_usd": im,
                "balance_usd": bal,
                "status": status,
                "balance_formatted": bal_f
            })
        facts["period_balances"] = period_balances

    return facts