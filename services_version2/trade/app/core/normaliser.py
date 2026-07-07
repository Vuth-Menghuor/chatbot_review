"""Normalise raw DAL responses into the final JSON shape."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from app.core.countries import ASEAN_MEMBER_CODES, EU_MEMBER_CODES
from app.core.countries import CODE_TO_COUNTRY_NAME as COUNTRY_NAMES
from app.core.exceptions import NormalisationError
from app.core.transport_modes import TRANSPORT_MODE_DISPLAY_NAMES

# Reverse lookup: full country name (uppercase) → ISO-2 code
_NAME_TO_CODE = {v.upper(): k for k, v in COUNTRY_NAMES.items()}

_TRANSPORT_NAMES = TRANSPORT_MODE_DISPLAY_NAMES


def compute_growth_rates(
    records: list[dict[str, Any]],
    query_params: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Calculate period-over-period percentage growth rates.

    SOLE AUTHORITY for all growth computation. enrichment.py only expands time scope.
    Returns (result_records, data_quality) where data_quality["growth_valid"] is the
    single canonical truth flag consumed by NLG, chart_mapper, and summary builders.

    Section 22: When a trade-bloc query is detected (PARTNER_COUNTRY is a list of >3
    countries, or extra.trade_bloc is set), records are pre-aggregated to one total per
    period before growth computation so the result is a single bloc-level rate.
    """
    params = query_params or {}
    metrics_list = params.get("metrics") or ["VALUE_USD"]
    value_key = metrics_list[0] if metrics_list else "VALUE_USD"

    # Normalise value_key against actual row keys (case-insensitive)
    if records:
        for k in records[0].keys():
            if k.upper() == value_key.upper():
                value_key = k
                break

    period_key = None
    if records:
        for k in ["PERIOD", "period", "Period"]:
            if k in records[0]:
                period_key = k
                break

    empty_quality: dict[str, Any] = {"growth_valid": False, "distinct_period_count": 0}
    if not period_key:
        return records, empty_quality

    # ------------------------------------------------------------------ #
    # Section 22: Bloc-level pre-aggregation                              #
    # ------------------------------------------------------------------ #
    filters = params.get("filters") or {}
    extra = params.get("extra") or {}
    partner_filter = filters.get("PARTNER_COUNTRY", [])
    is_bloc_query = (
        extra.get("trade_bloc")
        or (isinstance(partner_filter, list) and len(partner_filter) > 3)
    )
    if is_bloc_query and records:
        from collections import defaultdict
        bloc_totals: dict[str, dict[str, Any]] = defaultdict(lambda: {value_key: 0.0, period_key: None})
        for r in records:
            p = str(r.get(period_key, ""))
            try:
                bloc_totals[p][value_key] += float(r.get(value_key) or 0)
            except (ValueError, TypeError):
                pass
            bloc_totals[p][period_key] = p
        records = [dict(v) for v in bloc_totals.values()]

    # ------------------------------------------------------------------ #
    # Resolve group key                                                   #
    # ------------------------------------------------------------------ #
    group_key: str | None = None
    if params.get("group_by"):
        group_key = params["group_by"][0]
        if records:
            for k in records[0].keys():
                if k.lower() == group_key.lower():
                    group_key = k
                    break

    result_records: list[dict[str, Any]] = []

    def _growth(curr: float, prev: float) -> float | None:
        """Return growth % or None when baseline is missing/zero."""
        if prev == 0:
            return None
        return round(((curr - prev) / prev) * 100, 2)

    if group_key and group_key != period_key:
        groups: dict[Any, list] = {}
        for r in records:
            g_val = r.get(group_key)
            groups.setdefault(g_val, []).append(r)

        for g_val, g_records in groups.items():
            g_records.sort(key=lambda x: str(x.get(period_key, "")))
            for i, r in enumerate(g_records):
                # Baseline record: no prior period → growth is undefined, never 0.0
                r["growth_rate_pct"] = None if i == 0 else _growth(
                    float(r.get(value_key) or 0),
                    float(g_records[i - 1].get(value_key) or 0),
                )
                result_records.append(r)
    else:
        records_copy = [dict(r) for r in records]
        records_copy.sort(key=lambda x: str(x.get(period_key, "")))
        for i, r in enumerate(records_copy):
            r["growth_rate_pct"] = None if i == 0 else _growth(
                float(r.get(value_key) or 0),
                float(records_copy[i - 1].get(value_key) or 0),
            )
        result_records = records_copy

    # ------------------------------------------------------------------ #
    # Single canonical data_quality truth flag (Section 19)              #
    # ------------------------------------------------------------------ #
    distinct_periods = len(set(str(r.get(period_key, "")) for r in result_records if r.get(period_key)))
    data_quality: dict[str, Any] = {
        "growth_valid": distinct_periods >= 2,
        "distinct_period_count": distinct_periods,
    }

    # Full multi-period series is preserved — callers must NOT strip baseline periods.
    return result_records, data_quality




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

    # Strip trailing \r\n and whitespace (B1) and consistently normalize null dimensions (B3)
    target_clean_keys = {"HS_CHAPTER", "HS_HEADING", "HS_CODE", "SITC_SECTION", "SITC_DIVISION"}
    standard_dims = {"SITC_SECTION", "SITC_DIVISION", "HS_CHAPTER", "HS_HEADING", "HS_CODE", "MODE_OF_TRANSPORT", "PARTNER_COUNTRY"}
    standard_dims_lower = {d.lower() for d in standard_dims}

    group_dims = set()
    if query_params:
        for key in ("group_by", "dimensions"):
            vals = query_params.get(key)
            if isinstance(vals, list):
                for v in vals:
                    group_dims.add(str(v).upper())

    cleaned_records = []
    for r in records:
        r_copy = dict(r)
        for k in list(r_copy.keys()):
            # B1: Strip newlines and spaces
            if k.upper() in target_clean_keys and isinstance(r_copy[k], str):
                r_copy[k] = r_copy[k].replace('\r', '').replace('\n', '').strip()

            # B3: Normalize nulls/missing/empty values
            if k.upper() in standard_dims or k.lower() in standard_dims_lower or k.upper() in group_dims:
                val = r_copy.get(k)
                if val is None or str(val).strip() == "" or str(val).lower() == "null":
                    r_copy[k] = "Other"
                    if k.upper() == "PARTNER_COUNTRY" or k.lower() == "partner_country":
                        logger.warning("PARTNER_COUNTRY is null or unmapped in normaliser. Normalizing to 'Other'.")

            # Translate Mode of Transport code to name
            if k.upper() == "MODE_OF_TRANSPORT":
                val = str(r_copy.get(k)).strip()
                r_copy[k] = _TRANSPORT_NAMES.get(val, val)

        # Ensure all group_by / dimension keys from query params exist in r_copy
        for gd in group_dims:
            found_k = None
            for rk in r_copy.keys():
                if rk.upper() == gd.upper():
                    found_k = rk
                    break
            if found_k:
                val = r_copy[found_k]
                if val is None or str(val).strip() == "" or str(val).lower() == "null":
                    r_copy[found_k] = "Other"
                    if gd.upper() == "PARTNER_COUNTRY":
                        logger.warning("PARTNER_COUNTRY is null or unmapped in normaliser. Normalizing to 'Other'.")
            else:
                # Add missing grouped dimension as "Other"
                r_copy[gd] = "Other"
                if gd.upper() == "PARTNER_COUNTRY":
                    logger.warning("PARTNER_COUNTRY is null or unmapped in normaliser. Normalizing to 'Other'.")

        cleaned_records.append(r_copy)
    records = cleaned_records

    # ------------------------------------------------------------------ #
    # Section 28: General Trade Bloc Aggregation                         #
    # ------------------------------------------------------------------ #
    if intent != "ranking" and records and query_params:
        orig_partners = query_params.get("partner_countries") or []
        if not isinstance(orig_partners, list):
            orig_partners = [orig_partners]
        if query_params.get("partner_country"):
            orig_partners.append(query_params.get("partner_country"))

        has_eu = any(str(p).upper() == "EU" for p in orig_partners if p)
        has_asean = any(str(p).upper() == "ASEAN" for p in orig_partners if p)

        if has_eu or has_asean:
            mapped_records = []
            for r in records:
                r_copy = dict(r)
                country_key = next((k for k in r_copy.keys() if k.upper() == "PARTNER_COUNTRY"), None)
                if country_key:
                    c_val = str(r_copy[country_key]).upper()
                    # DAL may return ISO codes OR full country names
                    country_code = _NAME_TO_CODE.get(c_val, c_val)
                    if has_eu and country_code in EU_MEMBER_CODES:
                        r_copy[country_key] = "EU"
                    elif has_asean and country_code in ASEAN_MEMBER_CODES:
                        r_copy[country_key] = "ASEAN"
                mapped_records.append(r_copy)

            # Consolidate duplicate records after mapping
            measure_keys = {"VALUE_USD", "NET_WEIGHT", "VALUE_KHR", "growth_rate_pct"}
            group_keys = [k for k in mapped_records[0].keys() if k not in measure_keys]

            consolidated = {}
            for r in mapped_records:
                group_val = tuple(r.get(k) for k in group_keys)
                if group_val not in consolidated:
                    consolidated[group_val] = dict(r)
                else:
                    target = consolidated[group_val]
                    for m in ["VALUE_USD", "NET_WEIGHT", "VALUE_KHR"]:
                        if m in r and r[m] is not None:
                            try:
                                target[m] = (target.get(m) or 0.0) + float(r[m])
                            except (ValueError, TypeError):
                                pass
            records = list(consolidated.values())

    # Filter records by requested period if single period summary/trade_balance intent
    did_filter = False
    if intent in ("summary", "trade_balance") and records and query_params:
        requested_period = query_params.get("period")
        start_p = query_params.get("start_period")
        end_p = query_params.get("end_period")

        period_key = next((k for k in records[0].keys() if k.upper() == "PERIOD"), None)
        if period_key:
            original_len = len(records)
            if requested_period:
                records = [r for r in records if str(r.get(period_key)).startswith(str(requested_period))]
            elif start_p and end_p and start_p == end_p:
                records = [r for r in records if str(r.get(period_key)).startswith(str(start_p))]
            if len(records) != original_len:
                did_filter = True

    # Section 19: growth computation — compute_growth_rates is the SOLE authority.
    _growth_data_quality: dict[str, Any] = {"growth_valid": False, "distinct_period_count": 0}
    if intent == "growth" and records:
        records, _growth_data_quality = compute_growth_rates(records, query_params)

        # Sort multi-entity growth queries by absolute growth rate or latest VALUE_USD (Rule 3)
        if _growth_data_quality.get("growth_valid") and len(records) > 0:
            entity_key = None
            for key in ["PARTNER_COUNTRY", "partner_country", "HS_HEADING", "hs_heading",
                        "SITC_DIVISION", "sitc_division", "MODE_OF_TRANSPORT", "mode_of_transport",
                        "HS_CHAPTER", "hs_chapter", "FLOW", "flow"]:
                if key in records[0]:
                    entity_key = key
                    break

            if entity_key:
                groups = {}
                for r in records:
                    ent = r.get(entity_key)
                    groups.setdefault(ent, []).append(r)

                question_lower = (query_params or {}).get("question", "").lower()
                is_fastest = any(kw in question_lower for kw in ["fastest", "rapid", "highest growth", "most growth"])

                if is_fastest:
                    entity_max_growth = {}
                    for ent, ent_recs in groups.items():
                        rates = [r.get("growth_rate_pct") for r in ent_recs if r.get("growth_rate_pct") is not None]
                        entity_max_growth[ent] = max(rates) if rates else None
                    sorted_entities = sorted(
                        groups.keys(),
                        key=lambda ent: abs(entity_max_growth[ent]) if entity_max_growth[ent] is not None else -1.0,
                        reverse=True
                    )
                else:
                    entity_latest_val = {}
                    for ent, ent_recs in groups.items():
                        sorted_ent_recs = sorted(ent_recs, key=lambda x: str(x.get("PERIOD", x.get("period", ""))))
                        latest_rec = sorted_ent_recs[-1]
                        val = 0.0
                        for k in ["VALUE_USD", "trade_value", "VALUE"]:
                            if k in latest_rec:
                                try:
                                    val = float(latest_rec[k] or 0.0)
                                except (ValueError, TypeError):
                                    pass
                                break
                        entity_latest_val[ent] = val
                    sorted_entities = sorted(groups.keys(), key=lambda ent: entity_latest_val[ent], reverse=True)

                user_limit = (query_params or {}).get("extra", {}).get("user_limit", 10)
                sorted_records = []
                for ent in sorted_entities[:user_limit]:
                    ent_recs = sorted(groups[ent], key=lambda x: str(x.get("PERIOD", x.get("period", ""))))
                    sorted_records.extend(ent_recs)
                records = sorted_records

    # Flow consolidation for ranking queries
    consolidate_flows = (query_params or {}).get("extra", {}).get("consolidate_flows", False)
    user_limit = (query_params or {}).get("extra", {}).get("user_limit", 10)

    if consolidate_flows and records:
        req_metrics = [str(m).upper() for m in (query_params or {}).get("metrics") or []]
        include_weight = any("WEIGHT" in m for m in req_metrics)

        totals = {}
        for r in records:
            country = r.get("PARTNER_COUNTRY") or r.get("partner_country")
            if not country:
                continue
            val = float(r.get("VALUE_USD", r.get("value_usd", r.get("trade_value", 0.0))) or 0.0)
            weight = float(r.get("NET_WEIGHT", r.get("net_weight", r.get("weight_kg", 0.0))) or 0.0) if include_weight else 0.0

            if country not in totals:
                entry = {
                    "PARTNER_COUNTRY": country,
                    "VALUE_USD": 0.0,
                    "PERIOD": r.get("PERIOD") or r.get("period"),
                    "FREQUENCY": r.get("FREQUENCY") or r.get("frequency"),
                }
                if include_weight:
                    entry["NET_WEIGHT"] = 0.0
                totals[country] = entry
            totals[country]["VALUE_USD"] += val
            if include_weight:
                totals[country]["NET_WEIGHT"] += weight

        sort_order = (query_params or {}).get("sort_order", "desc")
        reverse_sort = (str(sort_order).lower() != "asc")

        sort_field = "VALUE_USD"
        sort_param = (query_params or {}).get("sort") or ""
        if "NET_WEIGHT" in sort_param.upper() or "WEIGHT" in sort_param.upper():
            sort_field = "NET_WEIGHT"

        consolidated_records = sorted(
            totals.values(),
            key=lambda x: x.get(sort_field, x.get("VALUE_USD", 0.0)),
            reverse=reverse_sort
        )
        records = consolidated_records[:user_limit]

    count = len(records)

    default_flow = (query_params or {}).get("trade_direction") or \
                   (query_params or {}).get("filters", {}).get("FLOW")
    if isinstance(default_flow, list) and len(default_flow) == 1:
        default_flow = default_flow[0]
    default_flow_str = str(default_flow).upper() if default_flow else None

    # Always recalculate summary values dynamically based on finalized/filtered records
    if records:
        exports = 0.0
        imports = 0.0
        exports_weight = 0.0
        imports_weight = 0.0

        for r in records:
            flow_val = None
            for k in r.keys():
                if k.upper() == "FLOW":
                    flow_val = r[k]
                    break

            if flow_val is None:
                flow_str = default_flow_str
            else:
                flow_str = str(flow_val).upper()

            val = 0.0
            for k in r.keys():
                if k.upper() in ("VALUE_USD", "TRADE_VALUE", "VALUE"):
                    try:
                        val = float(r[k] or 0.0)
                        break
                    except (ValueError, TypeError):
                        pass

            weight = 0.0
            for k in r.keys():
                if k.upper() in ("NET_WEIGHT", "WEIGHT_KG", "NET_WEIGHT_KG"):
                    try:
                        weight = float(r[k] or 0.0)
                        break
                    except (ValueError, TypeError):
                        pass

            if flow_str == "EX":
                exports += val
                exports_weight += weight
            elif flow_str == "IM":
                imports += val
                imports_weight += weight
            else:
                exports += val
                exports_weight += weight

        # Count the number of EX and IM rows present
        ex_count = sum(1 for r in records if str(r.get("FLOW", r.get("flow", ""))).upper() == "EX")
        im_count = sum(1 for r in records if str(r.get("FLOW", r.get("flow", ""))).upper() == "IM")
        has_both_flows = (ex_count > 0 and im_count > 0)

        # Check if weight was explicitly requested
        req_metrics = [str(m).upper() for m in (query_params or {}).get("metrics") or []]
        has_weight = any("WEIGHT" in m for m in req_metrics)
        has_value_metric = "VALUE_USD" in req_metrics or len(req_metrics) == 0

        summary = {}
        if has_value_metric:
            summary["currency"] = "USD"
            if intent == "ranking":
                summary["subset_total_value"] = exports + imports
                summary["subset_count"] = count
                sort_order = (query_params or {}).get("sort_order", "desc")
                subset_label = f"top {count}" if str(sort_order).lower() != "asc" else f"bottom {count}"
                summary["subset_label"] = subset_label
            else:
                summary["total_trade_value"] = exports + imports
        else:
            summary["total_trade_value"] = None

        if has_weight:
            if intent == "ranking":
                summary["subset_total_weight"] = exports_weight + imports_weight
            else:
                summary["total_weight_kg"] = exports_weight + imports_weight
        else:
            summary["total_weight_kg"] = None

        # Section 23 extension: growth intent also nulls out value fields when VALUE_USD not requested
        if intent == "trade_balance" or (intent == "summary" and has_both_flows):
            summary["trade_balance"] = exports - imports
            if has_weight:
                summary["net_weight_balance"] = exports_weight - imports_weight

        # Section 19: Write execution_mode and data_quality for growth queries
        if intent == "growth":
            summary["data_quality"] = _growth_data_quality
            summary["execution_mode"] = "growth" if _growth_data_quality["growth_valid"] else "summary"
            if summary["execution_mode"] == "summary":
                summary["growth_downgrade_reason"] = "Insufficient baseline data — prior period not available."
            # Section 23/17 extension: null out value fields when VALUE_USD not requested under growth
            if not has_value_metric:
                summary.pop("total_trade_value", None)
                summary.pop("currency", None)
    else:
        req_metrics = [str(m).upper() for m in (query_params or {}).get("metrics") or []]
        has_weight = any("WEIGHT" in m for m in req_metrics)
        has_value_metric = "VALUE_USD" in req_metrics or len(req_metrics) == 0
        summary = {}
        if has_value_metric:
            summary["currency"] = "USD"
            if intent == "ranking":
                summary["subset_total_value"] = 0.0
                summary["subset_count"] = 0
                zero_sort_order = (query_params or {}).get("sort_order", "desc")
                zero_label = "top" if str(zero_sort_order).lower() != "asc" else "bottom"
                summary["subset_label"] = f"{zero_label} 0"
            else:
                summary["total_trade_value"] = 0.0
        else:
            summary["total_trade_value"] = None

        if has_weight:
            if intent == "ranking":
                summary["subset_total_weight"] = 0.0
            else:
                summary["total_weight_kg"] = 0.0
        else:
            summary["total_weight_kg"] = None

    # Merge DAL metadata
    metadata = dict(dal_response.get("metadata") or {})
    metadata.pop("scopes", None)
    metadata["intent"] = intent
    metadata["count"] = count

    # Centralised data quality annotation (Fixes #1, #4, #5, #12)
    _apply_data_quality_notes(summary, records, query_params, total_raw_count=count)

    # Generate frontend-ready visualization payloads
    from app.visualization import generate_visualizations
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


def _apply_data_quality_notes(
    summary: dict,
    records: list,
    query_params: dict | None,
    total_raw_count: int = 0,
) -> None:
    """Centralised data-quality annotation written into summary['data_quality'].

    Handles:
    - is_partial_period: any returned PERIOD is the current in-progress year (#1)
    - has_more: returned row count < total available due to user_limit cap (#4)
    - period_coverage_note: actual returned range narrower than requested (#5)
    All existing data_quality keys are preserved (e.g. growth_valid).
    """
    import datetime
    current_year = datetime.datetime.now().year

    dq = summary.get("data_quality") or {}

    # ── Fix #1: partial-period flag ───────────────────────────────────────────
    periods_in_records = set()
    for r in records:
        for k in r:
            if k.upper() == "PERIOD":
                p = str(r[k])
                if p[:4].isdigit():
                    periods_in_records.add(int(p[:4]))
                break

    if current_year in periods_in_records:
        dq["is_partial_period"] = True
        dq["partial_year"] = current_year
        dq["partial_year_note"] = (
            f"{current_year} data is year-to-date only and may understate the full-year figure."
        )
    else:
        dq.setdefault("is_partial_period", False)

    # ── Fix #4: has_more / truncation flag ────────────────────────────────────
    extra = (query_params or {}).get("extra") or {}
    user_limit = extra.get("user_limit")
    if user_limit and total_raw_count >= user_limit:
        dq["has_more"] = True
        dq["shown_count"] = total_raw_count
        dq["truncation_note"] = (
            f"Showing {total_raw_count} results — the total shown may not represent the full market."
        )
    else:
        dq.setdefault("has_more", False)

    # ── Fix #5: period-coverage gap ───────────────────────────────────────────
    req_start = (query_params or {}).get("start_period")
    req_end = (query_params or {}).get("end_period")
    if req_start and req_end and periods_in_records:
        try:
            req_start_yr = int(str(req_start)[:4])
            req_end_yr = int(str(req_end)[:4])
            actual_min = min(periods_in_records)
            actual_max = max(periods_in_records)
            if actual_min > req_start_yr or actual_max < req_end_yr:
                dq["period_coverage_note"] = (
                    f"Data available from {actual_min} to {actual_max} only "
                    f"(requested {req_start_yr}–{req_end_yr})."
                )
                dq["actual_period_range"] = [actual_min, actual_max]
                dq["requested_period_range"] = [req_start_yr, req_end_yr]
        except (ValueError, TypeError):
            pass

    # ── Fix #3: period-mismatch check ─────────────────────────────────────────
    if extra.get("period_mismatch"):
        dq["period_mismatch"] = True
        dq["requested_period"] = extra.get("requested_period")
        dq["returned_period"] = extra.get("returned_period")
        dq["period_mismatch_note"] = (
            f"Note: Requested data for {extra.get('requested_period')}, "
            f"but displaying {extra.get('returned_period')} data."
        )

    if dq:
        summary["data_quality"] = dq
