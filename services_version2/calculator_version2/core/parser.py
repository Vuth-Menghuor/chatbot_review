"""
Natural Language Parser for Calculator Service
Extracts calculation parameters from user queries.
"""

from __future__ import annotations
import re
from typing import Any, Dict, Optional

KNOWN_COUNTRIES = {
    "china", "thailand", "vietnam", "japan", "south korea", "korea", "india",
    "indonesia", "philippines", "malaysia", "singapore", "hong kong", "taiwan",
    "bangladesh", "pakistan", "sri lanka", "laos", "myanmar", "cambodia",
    "usa", "united states", "america", "canada", "mexico", "brazil", "argentina", "chile",
    "germany", "france", "italy", "spain", "netherlands", "belgium", "austria", "greece",
    "poland", "united kingdom", "uk", "great britain", "switzerland", "sweden", "norway", "denmark",
    "czech republic", "hungary", "romania", "russia", "ukraine",
    "saudi arabia", "united arab emirates", "uae", "qatar", "kuwait", "bahrain", "oman",
    "yemen", "israel", "jordan", "lebanon", "iraq", "iran", "turkey",
    "south africa", "egypt", "nigeria", "ethiopia", "kenya",
    "australia", "new zealand"
}

def sanitize_currency_text(text: str) -> str:
    """Normalize common mojibake currency symbols before parsing."""
    if not text:
        return text

    normalized = text
    replacements = {
        "Â¥": "¥",
        "â‚¹": "₹",
        "ï¿¥": "¥",
        "＄": "$",
    }
    for broken, clean in replacements.items():
        normalized = normalized.replace(broken, clean)

    return normalized

def extract_explicit_currency(question: str) -> Optional[str]:
    """Extract user-provided currency from symbols, ISO codes, or common names."""
    q = sanitize_currency_text(question)
    token_pattern = (
        r"USD|CNY|KHR|EUR|GBP|THB|VND|JPY|KRW|INR|"
        r"dollars?|bucks?|greenbacks?|quid|pounds?|yuan|rmb|renminbi|riels?|yen|"
        r"[$¥៛€£฿₫₩₹]"
    )

    for match in re.finditer(token_pattern, q, re.IGNORECASE):
        normalized = normalize_currency_token(match.group(0))
        if normalized:
            return normalized

    return None

def normalize_currency_token(token: str) -> Optional[str]:
    """Normalize a currency token/symbol to ISO currency code."""
    if not token:
        return None

    cleaned = sanitize_currency_text(token).strip().lower()
    alias_map = {
        "usd": "USD", "dollar": "USD", "dollars": "USD", "buck": "USD", "bucks": "USD", "greenback": "USD", "greenbacks": "USD", "$": "USD",
        "cny": "CNY", "yuan": "CNY", "rmb": "CNY", "renminbi": "CNY", "¥": "CNY",
        "khr": "KHR", "riel": "KHR", "riels": "KHR", "៛": "KHR",
        "eur": "EUR", "euro": "EUR", "euros": "EUR", "€": "EUR",
        "gbp": "GBP", "pound": "GBP", "pounds": "GBP", "quid": "GBP", "£": "GBP",
        "thb": "THB", "baht": "THB", "฿": "THB",
        "vnd": "VND", "dong": "VND", "₫": "VND",
        "jpy": "JPY", "yen": "JPY",
        "krw": "KRW", "won": "KRW", "₩": "KRW",
        "inr": "INR", "rupee": "INR", "rupees": "INR", "₹": "INR",
    }
    return alias_map.get(cleaned)

def extract_amount_and_currency(question: str) -> Dict[str, Any]:
    """Extract customs value + currency from flexible user formats."""
    q = sanitize_currency_text(question)
    number_pattern = r"(?P<amt>\d+(?:,\d{3})*(?:\.\d{1,2})?)"
    token_pattern = (
        r"(?P<cur>USD|CNY|KHR|EUR|GBP|THB|VND|JPY|KRW|INR|"
        r"dollars?|bucks?|greenbacks?|quid|pounds?|yuan|rmb|renminbi|riels?|yen|[$¥៛€£฿₫₩₹])"
    )

    patterns = [
        rf"{token_pattern}\s*{number_pattern}",  # USD 8000, $8000, ¥8000
        rf"{number_pattern}\s*{token_pattern}",  # 8000USD, 8000 usd, 8000$
    ]

    for pattern in patterns:
        match = re.search(pattern, q, re.IGNORECASE)
        if not match:
            continue

        amount_raw = (match.group("amt") or "").replace(",", "")
        currency_raw = match.group("cur")
        currency = normalize_currency_token(currency_raw)

        if not currency:
            continue

        try:
            amount = float(amount_raw)
        except ValueError:
            continue

        return {
            "cif_value": amount,
            "currency": currency,
            "currency_provided": True,
        }

    return {
        "cif_value": None,
        "currency": None,
        "currency_provided": False,
    }

def parse_question_for_calculation(question: str) -> Dict[str, Any]:
    """Parse natural language question to extract calculation parameters."""
    sanitized_question = sanitize_currency_text(question)

    params = {
        "description": sanitized_question,
        "hs_code": None,
        "cif_value": None,
        "currency": None,
        "currency_provided": False,
        "origin_country": None,
        "quantity": None,
        "unit": None,
        "regime": "import"
    }

    q_lower = sanitized_question.lower()

    explicit_currency = extract_explicit_currency(sanitized_question)
    if explicit_currency:
        params["currency"] = explicit_currency
        params["currency_provided"] = True

    # Extract HS code (ordered from longest to shortest digits match)
    hs_patterns = [
        r'hs\s+code\s+(\d{8}|\d{6}|\d{4}(?:\.\d{2}){0,2})',
        r'hs\s+(\d{8}|\d{6}|\d{4}(?:\.\d{2}){0,2})',
        r'(\d{8})',
        r'(\d{4}\.\d{2}\.\d{2})',
        r'(\d{4}\.\d{2})',
        r'(\d{6})',
        r'(?:code\s+)?(\d{4}(?:\s+\d{2}){1,2})',
    ]
    for pattern in hs_patterns:
        match = re.search(pattern, q_lower)
        if match:
            hs_code = match.group(1).strip()
            if hs_code.isdigit():
                if len(hs_code) == 8:
                    hs_code = f"{hs_code[:4]}.{hs_code[4:6]}.{hs_code[6:8]}"
                elif len(hs_code) == 6:
                    hs_code = f"{hs_code[:4]}.{hs_code[4:6]}"
            else:
                hs_code = hs_code.replace(' ', '.')
            params["hs_code"] = hs_code
            break

    amount_currency = extract_amount_and_currency(sanitized_question)
    if amount_currency["cif_value"] is not None:
        params["cif_value"] = amount_currency["cif_value"]
    if amount_currency["currency"] and not params["currency_provided"]:
        params["currency"] = amount_currency["currency"]
        params["currency_provided"] = amount_currency["currency_provided"]

    # Fallback amount extraction
    if params["cif_value"] is None:
        cif_only_match = re.search(r'cif\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)', sanitized_question, re.IGNORECASE)
        if cif_only_match:
            try:
                params["cif_value"] = float(cif_only_match.group(1).replace(',', ''))
            except ValueError:
                pass

    # Extract origin country
    # 1. Look for specific country mentions using prefixes
    country_prefixes = ["from", "origin", "of", "import from", "imported from", "export to", "exported to", "to"]
    for prefix in country_prefixes:
        for country in KNOWN_COUNTRIES:
            pattern = rf"\b{re.escape(prefix)}\s+{re.escape(country)}\b"
            if re.search(pattern, q_lower):
                params["origin_country"] = country.title()
                break
        if params["origin_country"]:
            break

    # 2. Fallback: Search any known country anywhere in the query
    if not params["origin_country"]:
        for country in KNOWN_COUNTRIES:
            if re.search(rf"\b{re.escape(country)}\b", q_lower):
                params["origin_country"] = country.title()
                break

    if not params["currency"] and not params["origin_country"]:
        params["currency"] = "KHR"

    # FTA mentions
    cert_map = {
        "form d": "ATIGA",
        "form e": "ACFTA",
        "form ak": "AKFTA",
        "form aj": "AJCEP",
        "form rcep": "RCEP",
        "form aanz": "AANZFTA",
        "form aan": "AANZFTA",
        "acfta": "ACFTA",
        "atiga": "ATIGA",
        "rcep": "RCEP",
        "akfta": "AKFTA",
        "ajcep": "AJCEP",
    }

    for pattern, cert_type in cert_map.items():
        if re.search(rf"\b{re.escape(pattern)}\b", q_lower):
            params["fta_applicable"] = True
            params["fta_certificate_type"] = cert_type
            break

    if not params.get("fta_certificate_type"):
        fta_match = re.search(r"\b(acfta|atiga|fta|rcep|cptpp|akfta|ajcep)\b", q_lower, re.IGNORECASE)
        if fta_match:
            fta_code = fta_match.group(1).upper()
            params["fta_applicable"] = True
            params["fta_certificate_type"] = fta_code

    cert_origin_map = {
        "ATIGA": "VN",
        "ACFTA": "CN",
        "AKFTA": "KR",
        "AJCEP": "JP",
        "RCEP": "CN",
        "AANZFTA": "AU",
        "AIFTA": "IN",
    }
    cert = params.get("fta_certificate_type")
    if cert and cert in cert_origin_map:
        if not params.get("origin_country"):
            params["origin_country"] = cert_origin_map[cert]

    if params.get("fta_certificate_type") in ("ACFTA", "ATIGA", "AKFTA", "AJCEP"):
        params["preferential_cd_rate"] = 0

    qty_match = re.search(r'(\d+)\s*(?:head|unit|pcs|pieces|kg|liter|meter)', q_lower)
    if qty_match:
        params["quantity"] = float(qty_match.group(1))
        unit_match = re.search(r'(\d+)\s*(\w+)$', qty_match.group(0))
        if unit_match:
            params["unit"] = unit_match.group(2).lower()

    dq_match = re.search(r'\bdq\s*(?:=\s*)?(\d+(?:\.\d+)?)\s*(%?)', q_lower)
    if dq_match:
        val_str = dq_match.group(1)
        is_pct = dq_match.group(2) == '%'
        try:
            val = float(val_str)
            if is_pct or val > 1.0:
                val = val / 100.0
            params["dq_factor"] = val
            params["dq_applicable"] = True
        except ValueError:
            pass

    dv_match = re.search(r'\bdv\s*(?:=\s*)?(\d+(?:\.\d+)?)', q_lower)
    if dv_match:
        try:
            params["declared_value"] = float(dv_match.group(1))
        except ValueError:
            pass

    petroleum_terms = ["petrol", "fuel", "gasoline", "diesel", "petroleum", "oil", "car", "vehicle", "truck","ev"]
    if any(kw in q_lower for kw in petroleum_terms):
        params["petroleum_case"] = True

    mass_match = re.search(r'(?:net\s+mass\s+)?(\d+(?:\.\d+)?)\s*kg', q_lower)
    if mass_match:
        params["net_mass"] = float(mass_match.group(1))

    volume_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:l\b|liters?)', q_lower)
    if volume_match:
        params["volume"] = float(volume_match.group(1))

    if (params.get("hs_code") and params["hs_code"].startswith("2710")) or any(
        term in q_lower
        for term in ["petrol", "fuel", "gasoline", "diesel", "petroleum"]):
        params["petroleum_case"] = True

    return params
