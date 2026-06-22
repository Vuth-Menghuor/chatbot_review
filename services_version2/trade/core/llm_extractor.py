"""Google Gemini LLM parameter extraction for Trade Data Queries.

PHASE 1 CHANGES (see PR notes):
  1. Removed `_correct_intent_by_keywords`. The LLM already receives an explicit
     "Intent selection guide" in SYSTEM_INSTRUCTION — re-classifying its output
     with substring matching afterwards just let a dumber system silently
     overrule a smarter one, with no logging of *why*. If intent accuracy is
     still poor after this change, the fix is better prompt examples / few-shot
     data, not a second classifier bolted on after the first.
  2. Regex extractors (`_extract_semester_params_regex`,
     `_extract_transport_modes_regex`) are now strictly FALLBACK ONLY — they
     fill a field only when the LLM left it empty. They never overwrite a
     value the LLM already produced. Every time a fallback actually fires,
     it's logged, so silent disagreements are now visible in logs.
  3. Added `retry_context` support to `extract_parameters_llm` so a caller
     (see core/service.py's repair loop) can re-prompt the model with the
     specific validation error from a failed query plan, instead of treating
     a bad first guess as final.
"""

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
DEFAULT_TIMEOUT_SEC = 20

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

STRICT RULES (CRITICAL):
1. INTENT OVERRIDES: 
   - If the user asks to compare TWO OR MORE distinct partner countries, the intent is ALWAYS "comparison", even if they use the word "trend". 
   - If the word "compare" is used for a SINGLE entity over time (e.g., "compare this year to last year"), the intent is ALWAYS "trend".
   - "trade_balance" takes absolute precedence over other intents if words like "balance", "surplus", "deficit", or "net trade" are present.
   
Use these signal words as a guide, but always reason about the FULL question rather than pattern-matching a single keyword in isolation:
- "ranking" signals: top, bottom, most, least, highest, lowest, largest, smallest, best, worst, leading
- "trend" signals: over time, monthly, quarterly, each year, per month, historical, how has ... changed
- "comparison" signals: compare, versus, vs, between, difference, relative to, against -- BUT only when TWO OR MORE distinct partner countries are being compared. "Compare this year to last year" for ONE country is a "trend" question, not "comparison".
- "breakdown" signals: breakdown, by product, by chapter, by sector, by transport, by mode, distribution of
- "growth" signals: growth, grew, declined, increase, decrease, year-over-year, YoY, faster, slower
- "trade_balance" signals: balance, surplus, deficit, net trade, more import than export -- these take precedence over other signals when present, since "balance" implies both EX and IM data are needed regardless of other phrasing.
- "summary" is the fallback ONLY when no comparison/trend/ranking/breakdown/growth/balance signal is present.

Parameters to extract:
- intent: one of ["summary", "ranking", "trend", "comparison", "breakdown", "growth", "trade_balance"]
- origin_country: Origin country name or ISO-2 code.
- destination_country: Destination country name or ISO-2 code.
- partner_countries: List of partner countries involved if comparison or ranking.
- year: A single year as integer.
- years: List of years as integers.
- semester: Integer (1 or 2). Use 1 for "first half", "H1", "S1", "first semester", "semester 1". Use 2 for "second half", "H2", "S2", "second semester", "semester 2". If the user says "semester" or "semi-annual" without specifying which one, default to 1. If the user mentions BOTH halves (e.g. "S1 to S2", "first and second half"), set start_period/end_period instead of semester (see below).
- start_period: Start year or period (e.g. "2022" for annual, "2022-Q1" for quarterly, "2022-S1" for semi-annual, "2022-01" for monthly) for time ranges.
- end_period: End year or period (e.g. "2025" for annual, "2025-Q4" for quarterly, "2025-S2" for semi-annual, "2025-12" for monthly) for time ranges.
- month: Month as integer (1-12).
- quarter: Quarter string ("Q1", "Q2", "Q3", "Q4"). Do NOT extract quarter if the user asked for semester/semi-annual (S1/S2).
- frequency: Frequency ("M"=monthly, "Q"=quarterly, "A"=annual, "S"=semi-annual).
- hs_chapter: 2-digit HS chapter code.
- hs_code: HS code (4-to-8 digits) OR product name/description (e.g., "rice", "garment", "electronics").
- mode_of_transport: Mode of transport (one of: "air", "sea", "land", "rail", "inland", "postal", "multimodal", "fixed"). If the question mentions MULTIPLE modes (e.g. "air and sea"), return a list of all of them.
- trade_direction: One of ["EX", "IM"]. "EX" for exports, selling, sending. "IM" for imports, buying, receiving.
- limit: Integer limit (e.g. for top N).
- sort_order: One of ["asc", "desc"] (e.g., "asc" for bottom/lowest, "desc" for top/highest).
- sort_metric: One of ["VALUE_USD", "NET_WEIGHT", "QUANTITY"].
- metrics: List from ["VALUE_USD", "VALUE_KHR", "NET_WEIGHT", "QUANTITY", "QUANTITY.UNIT"]. Use VALUE_KHR if user asks for "riel" or "KHR". Use NET_WEIGHT if user asks for "kg", "tonnes", "weight". Use QUANTITY + QUANTITY.UNIT together if user asks "how many [units/pieces/tonnes]".
- group_by: Dimensions to aggregate by. Choose from: "partner_country" (for country-level analysis), "mode_of_transport" (for transport channel breakdown), "hs_chapter" (for broad product category breakdown, 2-digit HS), "hs_heading" (for specific product breakdown, 4-digit HS), "sitc_section" (for economic sector/industry breakdown, SITC classification), "sitc_division" (for detailed industry breakdown, SITC 2-digit division), "flow" (to split exports vs imports), "period" (for time-series grouping).

Output a single JSON object with these keys. If a parameter is not present or cannot be inferred, set it to null.
Ensure South Korea / Republic of Korea is strictly mapped to ISO-2 code 'KR', not 'KP' (which is North Korea)."""


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


def extract_parameters_llm(question: str, retry_context: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Call Google Gemini REST API to extract structured query parameters from human question.

    Args:
        question: The natural language question.
        retry_context: Optional. When a prior attempt produced a query plan that
            failed validation, pass a short description of the validation error
            here. The model will be asked to correct its previous extraction.
            (See core/service.py's repair loop.)

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
    )

    if retry_context:
        prompt += (
            f"NOTE: A previous extraction attempt for this same question produced an invalid query.\n"
            f"Validation error: {retry_context}\n"
            f"Please correct the extraction so the error above does not recur.\n\n"
        )

    prompt += f"User Question: \"{question}\""

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
        logger.info(f"Invoking Gemini model '{model}' for parameter extraction (retry={bool(retry_context)})...")

        with httpx.Client(timeout=DEFAULT_TIMEOUT_SEC) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()

            candidates = result.get("candidates", [])
            if not candidates:
                logger.warning("Gemini response returned no candidates.")
                return None

            content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if not content_text:
                logger.warning("Gemini response content text is empty.")
                return None

            # Clean markdown code blocks before parsing
            content_text = content_text.replace("```json", "").replace("```", "").strip()
            parsed_raw = json.loads(content_text)

            logger.info(f"Gemini raw response parsed successfully: {parsed_raw}")

            processed = parse_and_resolve_parameters(parsed_raw, question)
            return processed

    except Exception as e:
        logger.error(f"Gemini LLM parameter extraction failed: {e}", exc_info=True)
        return None


def parse_and_resolve_parameters(raw: Dict[str, Any], question: str) -> Dict[str, Any]:
    """Resolve raw LLM parsed parameters to match expected types and structures in validation.py.

    PHASE 1: this function no longer re-classifies intent or overwrites
    LLM-provided values with regex matches. Regex is fallback-only now —
    it fills gaps the LLM left empty and never clobbers a value the LLM
    already set.
    """
    params: Dict[str, Any] = {}

    # Intent mapping (fallback to summary if invalid). We TRUST the LLM's
    # classification here -- it already has the full intent-selection guide
    # in SYSTEM_INSTRUCTION. No post-hoc keyword override.
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

    semester = raw.get("semester")
    if semester is not None:
        try:
            params["semester"] = int(semester)
            params["frequency"] = "S"
        except (ValueError, TypeError):
            pass

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
        if isinstance(mode_of_transport, list):
            params["mode_of_transport"] = [str(m).lower() for m in mode_of_transport if m]
        else:
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

    # Metrics
    metrics = raw.get("metrics")
    if isinstance(metrics, list):
        params["metrics"] = [str(m).upper() for m in metrics if m]
    elif isinstance(metrics, str) and metrics:
        params["metrics"] = [metrics.upper()]

    # Group by
    group_by = raw.get("group_by")
    if isinstance(group_by, list):
        params["group_by"] = [str(g) for g in group_by if g]
        params["dimensions"] = params["group_by"]
    elif isinstance(group_by, str) and group_by:
        params["group_by"] = [group_by]
        params["dimensions"] = [group_by]

    # --- FALLBACK-ONLY regex enrichment ---
    # These never overwrite a value the LLM already gave us. They only fill
    # gaps, and every fill is logged so silent disagreements are visible.
    _fill_semester_params_from_regex(params, question)
    _fill_transport_modes_from_regex(params, question)

    # Filter out None values
    return {k: v for k, v in params.items() if v is not None}


def _fill_semester_params_from_regex(params: Dict[str, Any], question: str) -> None:
    """Fallback ONLY: fill semester/period fields from regex if the LLM left them empty.

    Never overwrites params the LLM already set. If the LLM already produced
    a semester/year/period/frequency, this function is a no-op.
    """
    already_has_time_signal = any(
        params.get(k) is not None
        for k in ("semester", "start_period", "end_period", "frequency", "quarter", "month")
    )
    if already_has_time_signal:
        return

    regex_result = _extract_semester_params_regex(question)
    if not regex_result:
        return

    logger.info(f"[llm_extractor] LLM left time-period fields empty; regex fallback filled: {regex_result}")
    for k, v in regex_result.items():
        if v is not None:
            params.setdefault(k, v)
        # Note: explicit None from the regex extractor (used to mean "clear
        # single-semester in favor of a range") is intentionally ignored here
        # since we only ever fill gaps, never clear LLM-provided values.


def _fill_transport_modes_from_regex(params: Dict[str, Any], question: str) -> None:
    """Fallback ONLY: fill mode_of_transport from regex if the LLM left it empty."""
    if params.get("mode_of_transport"):
        return

    regex_modes = _extract_transport_modes_regex(question)
    if not regex_modes:
        return

    logger.info(f"[llm_extractor] LLM left mode_of_transport empty; regex fallback filled: {regex_modes}")
    params["mode_of_transport"] = regex_modes if len(regex_modes) > 1 else regex_modes[0]


def _extract_semester_params_regex(question: str) -> Dict[str, Any]:
    """Regex extractor for semi-annual (S1/S2) periods and ranges. FALLBACK ONLY -- see callers."""
    q = question.upper()
    params = {}

    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", q)]

    s1_patterns = [
        r"\bS1\b", r"\bH1\b",
        r"\bFIRST\s+HALF\b", r"\b1ST\s+HALF\b",
        r"\bFIRST\s+SEMESTER\b", r"\b1ST\s+SEMESTER\b",
        r"\bSEMESTER\s+1\b", r"\bSEM\s+1\b",
        r"\bSEMESTER1\b", r"\bSEM1\b"
    ]
    s2_patterns = [
        r"\bS2\b", r"\bH2\b",
        r"\bSECOND\s+HALF\b", r"\b2ND\s+HALF\b",
        r"\bSECOND\s+SEMESTER\b", r"\b2ND\s+SEMESTER\b",
        r"\bSEMESTER\s+2\b", r"\bSEM\s+2\b",
        r"\bSEMESTER2\b", r"\bSEM2\b"
    ]

    has_s1 = any(re.search(p, q) for p in s1_patterns)
    has_s2 = any(re.search(p, q) for p in s2_patterns)

    if has_s1 or has_s2:
        params["frequency"] = "S"
        import datetime
        default_year = datetime.datetime.now().year - 1

        if has_s1 and has_s2:
            if len(years) >= 2:
                params["start_period"] = f"{years[0]}-S1"
                params["end_period"] = f"{years[1]}-S2"
            elif len(years) == 1:
                params["start_period"] = f"{years[0]}-S1"
                params["end_period"] = f"{years[0]}-S2"
            else:
                params["start_period"] = f"{default_year}-S1"
                params["end_period"] = f"{default_year}-S2"
        elif has_s1:
            params["year"] = years[0] if years else default_year
            params["semester"] = 1
        elif has_s2:
            params["year"] = years[0] if years else default_year
            params["semester"] = 2

    return params


def _extract_transport_modes_regex(question: str) -> list[str]:
    """Regex extractor for transport modes. FALLBACK ONLY -- see callers."""
    q = question.lower()
    detected = []

    mappings = {
        "air": [r"\bair\b", r"\bplane\b", r"\bflight\b"],
        "sea": [r"\bsea\b", r"\bocean\b", r"\bship\b", r"\bvessel\b", r"\bmaritime\b"],
        "road": [r"\broad\b", r"\bland\b", r"\btruck\b"],
        "rail": [r"\brail\b", r"\btrain\b"],
        "postal": [r"\bpostal\b", r"\bpost\b", r"\bmail\b"],
        "inland": [r"\binland\b", r"\briver\b", r"\bcanal\b"],
        "multimodal": [r"\bmultimodal\b", r"\bmulti-modal\b"],
        "fixed": [r"\bfixed\b", r"\bpipeline\b"],
    }

    for mode, patterns in mappings.items():
        for pattern in patterns:
            if re.search(pattern, q):
                detected.append(mode)
                break

    return detected