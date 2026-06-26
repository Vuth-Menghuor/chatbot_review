from typing import Any, Dict

COUNTRY_NAMES = {
    "AD": "Andorra",
    "AE": "United Arab Emirates",
    "AF": "Afghanistan",
    "AG": "Antigua and Barbuda",
    "AI": "Anguilla",
    "AL": "Albania",
    "AM": "Armenia",
    "AO": "Angola",
    "AR": "Argentina",
    "AS": "American Samoa",
    "AT": "Austria",
    "AU": "Australia",
    "AW": "Aruba",
    "AZ": "Azerbaijan",
    "BA": "Bosnia and Herzegovina",
    "BB": "Barbados",
    "BD": "Bangladesh",
    "BE": "Belgium",
    "BF": "Burkina Faso",
    "BG": "Bulgaria",
    "BH": "Bahrain",
    "BI": "Burundi",
    "BJ": "Benin",
    "BM": "Bermuda",
    "BN": "Brunei",
    "BO": "Bolivia",
    "BR": "Brazil",
    "BS": "Bahamas",
    "BT": "Bhutan",
    "BW": "Botswana",
    "BY": "Belarus",
    "BZ": "Belize",
    "CA": "Canada",
    "CF": "Central African Republic",
    "CG": "Congo",
    "CH": "Switzerland",
    "CI": "Cote d'Ivoire",
    "CK": "Cook Islands",
    "CL": "Chile",
    "CM": "Cameroon",
    "CN": "China",
    "CO": "Colombia",
    "CR": "Costa Rica",
    "CU": "Cuba",
    "CV": "Cape Verde",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DJ": "Djibouti",
    "DK": "Denmark",
    "DM": "Dominica",
    "DO": "Dominican Republic",
    "DZ": "Algeria",
    "EC": "Ecuador",
    "EE": "Estonia",
    "EG": "Egypt",
    "ES": "Spain",
    "ET": "Ethiopia",
    "FI": "Finland",
    "FJ": "Fiji",
    "FR": "France",
    "GB": "United Kingdom",
    "GD": "Grenada",
    "GE": "Georgia",
    "GH": "Ghana",
    "GI": "Gibraltar",
    "GL": "Greenland",
    "GM": "Gambia",
    "GN": "Guinea",
    "GQ": "Equatorial Guinea",
    "GR": "Greece",
    "GT": "Guatemala",
    "GU": "Guam",
    "GW": "Guinea-Bissau",
    "GY": "Guyana",
    "HK": "Hong Kong",
    "HN": "Honduras",
    "HR": "Croatia",
    "HT": "Haiti",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IQ": "Iraq",
    "IR": "Iran",
    "IS": "Iceland",
    "IT": "Italy",
    "JM": "Jamaica",
    "JO": "Jordan",
    "JP": "Japan",
    "KE": "Kenya",
    "KG": "Kyrgyzstan",
    "KH": "Cambodia",
    "KI": "Kiribati",
    "KM": "Comoros",
    "KN": "Saint Kitts and Nevis",
    "KP": "North Korea",
    "KR": "South Korea",
    "KW": "Kuwait",
    "KY": "Cayman Islands",
    "KZ": "Kazakhstan",
    "LA": "Laos",
    "LB": "Lebanon",
    "LC": "Saint Lucia",
    "LI": "Liechtenstein",
    "LK": "Sri Lanka",
    "LR": "Liberia",
    "LS": "Lesotho",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "LY": "Libya",
    "MA": "Morocco",
    "MC": "Monaco",
    "MD": "Moldova",
    "ME": "Montenegro",
    "MG": "Madagascar",
    "MH": "Marshall Islands",
    "MK": "Macedonia",
    "ML": "Mali",
    "MM": "Myanmar",
    "MN": "Mongolia",
    "MO": "Macau",
    "MP": "Northern Mariana Islands",
    "MR": "Mauritania",
    "MS": "Montserrat",
    "MT": "Malta",
    "MU": "Mauritius",
    "MV": "Maldives",
    "MW": "Malawi",
    "MX": "Mexico",
    "MY": "Malaysia",
    "MZ": "Mozambique",
    "NA": "Namibia",
    "NC": "New Caledonia",
    "NE": "Niger",
    "NG": "Nigeria",
    "NI": "Nicaragua",
    "NL": "Netherlands",
    "NO": "Norway",
    "NP": "Nepal",
    "NR": "Nauru",
    "NU": "Niue",
    "NZ": "New Zealand",
    "OM": "Oman",
    "PA": "Panama",
    "PE": "Peru",
    "PF": "French Polynesia",
    "PG": "Papua New Guinea",
    "PH": "Philippines",
    "PK": "Pakistan",
    "PL": "Poland",
    "PM": "Saint Pierre and Miquelon",
    "PR": "Puerto Rico",
    "PT": "Portugal",
    "PW": "Palau",
    "PY": "Paraguay",
    "QA": "Qatar",
    "RE": "Reunion",
    "RO": "Romania",
    "RS": "Serbia",
    "RU": "Russia",
    "RW": "Rwanda",
    "SA": "Saudi Arabia",
    "SB": "Solomon Islands",
    "SC": "Seychelles",
    "SD": "Sudan",
    "SE": "Sweden",
    "SG": "Singapore",
    "SH": "Saint Helena",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "SL": "Sierra Leone",
    "SM": "San Marino",
    "SN": "Senegal",
    "SO": "Somalia",
    "SR": "Suriname",
    "ST": "Sao Tome and Principe",
    "SV": "El Salvador",
    "SY": "Syria",
    "SZ": "Swaziland",
    "TD": "Chad",
    "TG": "Togo",
    "TH": "Thailand",
    "TJ": "Tajikistan",
    "TK": "Tokelau",
    "TL": "Timor-Leste",
    "TM": "Turkmenistan",
    "TN": "Tunisia",
    "TO": "Tonga",
    "TR": "Turkey",
    "TT": "Trinidad and Tobago",
    "TV": "Tuvalu",
    "TW": "Taiwan",
    "TZ": "Tanzania",
    "UA": "Ukraine",
    "UG": "Uganda",
    "US": "United States",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VA": "Holy See",
    "VC": "Saint Vincent and the Grenadines",
    "VE": "Venezuela",
    "VG": "British Virgin Islands",
    "VI": "United States Virgin Islands",
    "VN": "Vietnam",
    "VU": "Vanuatu",
    "WF": "Wallis and Futuna",
    "WS": "Samoa",
    "YE": "Yemen",
    "YT": "Mayotte",
    "ZA": "South Africa",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}

TRANSPORT_NAMES = {
    "1": "sea",
    "2": "rail",
    "3": "road",
    "4": "air",
    "5": "postal",
    "6": "multimodal",
    "7": "fixed",
    "8": "inland waterway",
    "9": "other transport",
    "0": "unknown",
}

# Dimension keys that, when present in group_by, should trigger a per-group
# breakdown of facts rather than a single flattened total. Maps the
# dimension's column name in the raw record to a human-readable label key
# used in facts/messages.
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
        # Records may already contain a display string ("Air transport") or
        # a numeric code ("4") depending on source — normalize both.
        as_code = TRANSPORT_NAMES.get(str(raw_value))
        return as_code if as_code else raw_value
    return raw_value


def extract_facts(payload: Dict[str, Any], query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and format raw query facts from payload and query parameters."""
    intent = query_params.get("intent", "summary")

    # 1. Total trade values
    summary = payload.get("summary") or {}
    total_trade_value = summary.get("total_trade_value") or payload.get("total_trade_value") or 0.0

    records = payload.get("records") or []
    
    # Calculate sum of returned records (subset total)
    subset_trade_value = sum(float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0) for r in records)
    subset_weight = sum(float(r.get("NET_WEIGHT", r.get("net_weight", 0.0)) or 0.0) for r in records)

    is_global_total = bool(summary.get("total_trade_value") or payload.get("total_trade_value"))
    if not total_trade_value and intent == "summary" and records:
        total_trade_value = subset_trade_value
        is_global_total = True

    total_weight = 0.0
    if is_global_total:
        total_weight = sum(float(r.get("NET_WEIGHT", 0.0)) for r in records)

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

    # Transport mode (only set when the query is FILTERED to a single mode;
    # if the query is GROUPED by mode instead, this stays None and the
    # mode_breakdown_records logic below takes over).
    transport_raw = filters.get("MODE_OF_TRANSPORT") or query_params.get("mode_of_transport")
    mode_of_transport = TRANSPORT_NAMES.get(str(transport_raw), transport_raw) if transport_raw else None

    # Period
    period = query_params.get("period")
    start_period = query_params.get("start_period")
    end_period = query_params.get("end_period")

    time_context = period
    if not time_context:
        if start_period and end_period:
            time_context = f"from {start_period} to {end_period}"
        elif start_period:
            time_context = f"since {start_period}"
        elif end_period:
            time_context = f"until {end_period}"

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
        "sort_order": query_params.get("sort_order", "desc"),
        "limit": query_params.get("limit"),
        "metrics": query_params.get("metrics") or ["VALUE_USD"],
    }

    # Add product code context
    hs_code = filters.get("HS_CODE") or filters.get("HS_HEADING") or query_params.get("hs_code")
    hs_chapter = filters.get("HS_CHAPTER") or query_params.get("hs_chapter")
    if hs_code:
        facts["hs_code"] = hs_code
    elif hs_chapter:
        facts["hs_chapter"] = hs_chapter

    # 3. Detect grouped-by-dimension queries (e.g. trend/breakdown grouped by
    # MODE_OF_TRANSPORT) and build an explicit per-group breakdown so the
    # NLG layer can compare groups (e.g. air vs. sea) instead of collapsing
    # everything into one grand total.
    group_by = query_params.get("group_by") or query_params.get("dimensions") or []
    grouped_dim = next((dim for dim in group_by if dim in GROUPABLE_DIMENSIONS), None)

    if grouped_dim and records:
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

        # Keep the historical key name specifically for MODE_OF_TRANSPORT so
        # any existing consumers expecting "mode_breakdown_records" still work.
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
            country_comparison.append({"country": country_name, "trade_value_usd": val, "weight_kg": weight})
        facts["comparison_records"] = country_comparison

    # If ranking, list top records
    elif intent == "ranking" and records:
        top_records = []
        for r in records:
            lbl_key = "PARTNER_COUNTRY"
            if "HS_CHAPTER" in r:
                lbl_key = "HS_CHAPTER"
            elif "HS_HEADING" in r:
                lbl_key = "HS_HEADING"
            elif "MODE_OF_TRANSPORT" in r:
                lbl_key = "MODE_OF_TRANSPORT"
            
            lbl_val = r.get(lbl_key)
            if lbl_key == "PARTNER_COUNTRY" and lbl_val:
                lbl_val = COUNTRY_NAMES.get(str(lbl_val).upper(), lbl_val)
            elif lbl_key == "MODE_OF_TRANSPORT" and lbl_val:
                lbl_val = TRANSPORT_NAMES.get(str(lbl_val), lbl_val)
            
            val = float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0)
            weight = float(r.get("NET_WEIGHT", r.get("net_weight", 0.0)) or 0.0)
            top_records.append({"label": lbl_val, "trade_value_usd": val, "weight_kg": weight})
        facts["ranking_records"] = top_records

    # If growth, compute and attach rates
    elif intent == "growth" and records:
        growth_records = []
        for r in records:
            p = r.get("PERIOD") or r.get("period")
            val = float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0)
            weight = float(r.get("NET_WEIGHT", r.get("net_weight", 0.0)) or 0.0)
            growth_rate = float(r.get("growth_rate_pct", 0.0))
            growth_records.append({"period": p, "trade_value_usd": val, "growth_rate_pct": growth_rate, "weight_kg": weight})
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

    # If trade_balance, list all records
    elif intent == "trade_balance" and records:
        tb_records = []
        for r in records:
            p = r.get("PERIOD") or r.get("period")
            flow = r.get("FLOW") or r.get("flow")
            val = float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0)
            tb_records.append({"period": p, "flow": flow, "value_usd": val})
        facts["trade_balance_records"] = tb_records

    return facts