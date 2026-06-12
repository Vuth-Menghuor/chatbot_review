"""Google Gemini LLM parameter extraction for Trade Data Queries."""

import os
import re
import json
import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from .countries import COUNTRY_TO_CODE_MAP, VALID_COUNTRY_CODES

logger = logging.getLogger(__name__)

# Default configurations
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_TIMEOUT_SEC = 10

SYSTEM_INSTRUCTION = """You are an expert at parsing natural language trade query questions into structured search parameters for the trade data service.
Classify the intent and extract key parameters.

Intents:
- summary: Overall summary of trade value and weight. Default when query is simple and doesn't specify comparisons, rankings, trends, or breakdowns.
- ranking: Finding the top or bottom N partners or products (usually contains words like "top", "bottom", "most", "largest", "highest").
- trend: Performance over time (monthly, quarterly, yearly, or showing trend over years).
- comparison: Comparing trade metrics between multiple countries or flows side-by-side.
- breakdown: Trade values broken down by products, HS chapters, or modes of transport.
- growth: Growth rate comparisons, showing increase or decrease year-over-year or month-over-month.
- trade_balance: Finding exports vs imports balance for a country.

Parameters to extract:
- intent: one of ["summary", "ranking", "trend", "comparison", "breakdown", "growth", "trade_balance"]
- origin_country: Origin country name or ISO-2 code.
- destination_country: Destination country name or ISO-2 code.
- partner_countries: List of partner countries involved if comparison or ranking.
- year: A single year as integer.
- years: List of years as integers.
- start_period: Start year or period (e.g. "2022") for time ranges.
- end_period: End year or period (e.g. "2025") for time ranges.
- month: Month as integer (1-12).
- quarter: Quarter string ("Q1", "Q2", "Q3", "Q4").
- frequency: Frequency ("M" for monthly, "Q" for quarterly, "A" for annually).
- hs_chapter: 2-digit HS chapter code.
- hs_code: HS code (4-to-8 digits) OR product name/description (e.g., "rice", "garment", "electronics").
- mode_of_transport: Mode of transport (one of: "air", "sea", "land", "rail", "inland", "postal", "multimodal", "fixed").
- trade_direction: One of ["EX", "IM"]. "EX" for exports, selling, sending. "IM" for imports, buying, receiving.
- limit: Integer limit (e.g. for top N).
- sort_order: One of ["asc", "desc"] (e.g., "asc" for bottom/lowest, "desc" for top/highest).
- sort_metric: One of ["VALUE_USD", "NET_WEIGHT", "QUANTITY"].
- group_by: Dimensions to group by. One of ["partner_country", "mode_of_transport", "hs_chapter", "hs_heading", "hs_code", "flow", "period"].

Output a single JSON object with these keys. If a parameter is not present or cannot be inferred, set it to null."""


def resolve_country(country_text: Optional[str]) -> Optional[str]:
    """Map dynamic country text (e.g. "China", "vietnam") to ISO-2 country code."""
    if not country_text:
        return None
    
    country_clean = country_text.strip().upper()
    if country_clean in VALID_COUNTRY_CODES:
        return country_clean
    
    # Run through the COUNTRY_TO_CODE_MAP pattern registry
    for pattern, code in COUNTRY_TO_CODE_MAP.items():
        if re.search(pattern, country_text, re.IGNORECASE):
            return code
            
    return None


def extract_parameters_llm(question: str) -> Optional[Dict[str, Any]]:
    """
    Call Google Gemini REST API to extract structured query parameters from human question.
    
    Returns:
        Dict of parsed parameters or None if LLM unavailable/failed.
    """
    api_key = os.getenv("X_GOOG_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.debug("Neither X_GOOG_API_KEY nor GEMINI_API_KEY is set in environment. Skipping LLM extraction.")
        return None

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    # Get current year dynamically to resolve relative reference tags like "last year" or "this year"
    import datetime
    current_year = datetime.datetime.now().year

    # Construct content payload with current year context
    prompt = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"Context Information:\n"
        f"- Current Year: {current_year}\n\n"
        f"IMPORTANT: Resolve relative year references (e.g. \"last year\" -> {current_year - 1}, "
        f"\"this year\" -> {current_year}, \"past 3 years\" -> start_period: {current_year - 2}, end_period: {current_year}) "
        f"accurately relative to the Current Year ({current_year}).\n\n"
        f"User Question: \"{question}\""
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }

    try:
        logger.info(f"Invoking Gemini model '{model}' for parameter extraction...")
        
        # Use httpx.post directly
        with httpx.Client(timeout=DEFAULT_TIMEOUT_SEC) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            result = response.json()
            
            # Extract content text
            candidates = result.get("candidates", [])
            if not candidates:
                logger.warning("Gemini response returned no candidates.")
                return None
                
            content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if not content_text:
                logger.warning("Gemini response content text is empty.")
                return None
                
            parsed_raw = json.loads(content_text)
            logger.info(f"Gemini raw response parsed successfully: {parsed_raw}")
            
            # Resolve parameters to system expected structures
            processed = parse_and_resolve_parameters(parsed_raw, question)
            return processed
            
    except Exception as e:
        logger.error(f"Gemini LLM parameter extraction failed: {e}", exc_info=True)
        return None


def parse_and_resolve_parameters(raw: Dict[str, Any], question: str) -> Dict[str, Any]:
    """Resolve raw LLM parsed parameters to match expected types and structures in validation.py."""
    params: Dict[str, Any] = {}
    
    # Intent mapping (fallback to summary if invalid)
    valid_intents = {"summary", "ranking", "trend", "comparison", "breakdown", "growth", "trade_balance"}
    intent_val = str(raw.get("intent", "summary")).lower()
    params["intent"] = intent_val if intent_val in valid_intents else "summary"
    
    # Country resolution
    origin = raw.get("origin_country")
    dest = raw.get("destination_country")
    params["origin_country"] = resolve_country(origin)
    params["destination_country"] = resolve_country(dest)
    
    # Comparison partner countries resolution
    partner_countries = raw.get("partner_countries")
    partner_country = raw.get("partner_country")
    
    resolved_partners = []
    if isinstance(partner_countries, list):
        for pc in partner_countries:
            rc = resolve_country(pc)
            if rc and rc not in resolved_partners:
                resolved_partners.append(rc)
    elif isinstance(partner_countries, str) and partner_countries:
        rc = resolve_country(partner_countries)
        if rc:
            resolved_partners.append(rc)
            
    if partner_country:
        rc = resolve_country(partner_country)
        if rc and rc not in resolved_partners:
            resolved_partners.append(rc)
            
    if resolved_partners:
        params["partner_countries"] = resolved_partners
        if len(resolved_partners) == 1:
            params["partner_country"] = resolved_partners[0]
            
    # Period: single year vs range
    year = raw.get("year")
    if year is not None:
        try:
            params["year"] = int(year)
        except (ValueError, TypeError):
            pass
            
    years = raw.get("years")
    if isinstance(years, list):
        try:
            params["years"] = [int(y) for y in years]
        except (ValueError, TypeError):
            pass

    start_period = raw.get("start_period")
    if start_period is not None:
        params["start_period"] = str(start_period)
        
    end_period = raw.get("end_period")
    if end_period is not None:
        params["end_period"] = str(end_period)
        
    month = raw.get("month")
    if month is not None:
        try:
            params["month"] = int(month)
        except (ValueError, TypeError):
            pass
            
    quarter = raw.get("quarter")
    if quarter is not None:
        params["quarter"] = str(quarter).upper()
        
    frequency = raw.get("frequency")
    if frequency is not None:
        params["frequency"] = str(frequency).upper()
        
    # HS chapter extraction
    hs_chapter = raw.get("hs_chapter")
    if hs_chapter is not None:
        params["hs_chapter"] = str(hs_chapter).zfill(2)
        
    # HS code (could be digits or a product name string like "rice")
    hs_code = raw.get("hs_code")
    if hs_code is not None:
        params["hs_code"] = str(hs_code)
        
    # Transport mode
    mode_of_transport = raw.get("mode_of_transport")
    if mode_of_transport is not None:
        params["mode_of_transport"] = str(mode_of_transport).lower()
        
    # Trade direction
    trade_direction = raw.get("trade_direction")
    if trade_direction is not None:
        params["trade_direction"] = str(trade_direction).upper()
        
    # Sorting & Limits
    limit = raw.get("limit")
    if limit is not None:
        try:
            params["limit"] = int(limit)
        except (ValueError, TypeError):
            pass
            
    sort_order = raw.get("sort_order")
    if sort_order is not None:
        params["sort_order"] = str(sort_order).lower()
        
    sort_metric = raw.get("sort_metric")
    if sort_metric is not None:
        params["sort_metric"] = str(sort_metric).upper()
        
    # Group by
    group_by = raw.get("group_by")
    if isinstance(group_by, list):
        params["group_by"] = [str(g) for g in group_by if g]
        params["dimensions"] = params["group_by"]
    elif isinstance(group_by, str) and group_by:
        params["group_by"] = [group_by]
        params["dimensions"] = [group_by]
        
    # Filter out None values
    return {k: v for k, v in params.items() if v is not None}
