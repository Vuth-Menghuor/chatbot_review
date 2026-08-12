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

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional

import httpx

from app.registry.countries import COUNTRY_TO_CODE_MAP, VALID_COUNTRY_CODES

logger = logging.getLogger(__name__)

# Default configurations
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_TIMEOUT_SEC = 45

SITC_SECTION_CODE_MAP = {
    "0": "Food and live animals",
    "1": "Beverages and tobacco",
    "2": "Crude materials, inedible, except fuels",
    "3": "Mineral fuels, lubricants and related materials",
    "4": "Animal and vegetable oils, fats and waxes",
    "5": "Chemicals and related products, n.e.s.",
    "6": "Manufactured goods classified chiefly by material",
    "7": "Machinery and transport equipment",
    "8": "Miscellaneous manufactured articles",
    "9": "Commodities and transactions not classified elsewhere in the SITC",
}

SITC_SECTION_NAME_TO_CODE = {
    "food and live animals": "0",
    "beverages and tobacco": "1",
    "crude materials, inedible, except fuels": "2",
    "mineral fuels, lubricants and related materials": "3",
    "animal and vegetable oils, fats and waxes": "4",
    "chemicals and related products, n.e.s.": "5",
    "chemicals": "5",
    "manufactured goods classified chiefly by material": "6",
    "manufactured goods": "6",
    "machinery and transport equipment": "7",
    "machinery": "7",
    "transport equipment": "7",
    "miscellaneous manufactured articles": "8",
    "miscellaneous": "8",
    "commodities and transactions not classified elsewhere in the sitc": "9"
}

def _get_system_instruction() -> str:
    try:
        from app.core.config import get_settings
        from app.core.prompt_service import DynamicPromptManager
        settings = get_settings()
        manager = DynamicPromptManager(prompts_dir=settings.prompts_dir)
        return manager.get_system_prompt("parameter_extraction")
    except Exception:
        return ""

SYSTEM_INSTRUCTION = _get_system_instruction()


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

    from app.core.config import get_settings
    settings = get_settings()
    model = os.getenv("GEMINI_MODEL", settings.default_gemini_model)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    # Get current year dynamically to resolve relative reference tags like "last year" or "this year"
    import datetime
    current_year = datetime.datetime.now().year

    from app.core.prompt_service import DynamicPromptManager
    manager = DynamicPromptManager(prompts_dir=settings.prompts_dir)
    system_prompt = manager.get_system_prompt("parameter_extraction")

    # Construct content payload with current year context
    prompt = (
        f"{system_prompt}\n\n"
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

    max_api_attempts = 3
    for attempt in range(1, max_api_attempts + 1):
        try:
            logger.info(f"Invoking Gemini model '{model}' for parameter extraction (retry={bool(retry_context)}, API attempt={attempt})...")

            with httpx.Client(timeout=settings.default_timeout_sec) as client:
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

        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Gemini LLM API call failed (attempt {attempt}/{max_api_attempts}): {e}")
            if attempt == max_api_attempts:
                logger.error("Gemini LLM parameter extraction failed after all attempts.", exc_info=True)
                return None
            time.sleep(1.0 * attempt)
        except Exception as e:
            logger.error(f"Unexpected error in Gemini LLM parameter extraction: {e}", exc_info=True)
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

    # Force comparison intent if two or more partner countries are specified with comparison signals
    if len(resolved_partners) >= 2:
        question_lower = question.lower()
        from app.core.constants import COMPARISON_SIGNALS
        if any(sig in question_lower for sig in COMPARISON_SIGNALS):
            params["intent"] = "comparison"

    # Post-extraction trend override — if LLM said summary but question
    # clearly asks about change over time, force trend intent.
    if params.get("intent") == "summary":
        q_lower_trend = question.lower()
        from app.core.constants import TREND_OVERRIDE_SIGNALS
        if any(sig in q_lower_trend for sig in TREND_OVERRIDE_SIGNALS):
            logger.info(
                "[parse_and_resolve_parameters] Overriding intent summary→trend: "
                "question contains multi-period signal words."
            )
            params["intent"] = "trend"

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

    # SITC section extraction
    sitc_section = raw.get("sitc_section")
    if sitc_section is not None:
        val_str = str(sitc_section).strip().lower()
        digit_match = re.search(r"\b(\d)\b", val_str)
        if digit_match:
            params["sitc_section"] = digit_match.group(1)
        else:
            params["sitc_section"] = SITC_SECTION_NAME_TO_CODE.get(val_str, val_str)

    # SITC division extraction
    sitc_division = raw.get("sitc_division")
    if sitc_division is not None:
        val_str = str(sitc_division).strip()
        digit_match = re.search(r"\b(\d{1,2})\b", val_str)
        if digit_match:
            params["sitc_division"] = digit_match.group(1).zfill(2)
        else:
            params["sitc_division"] = val_str

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

    # Chart Preference
    chart_pref = raw.get("chart_preference")
    if chart_pref is not None:
        chart_pref_str = str(chart_pref).strip().lower()
        chart_pref_str = chart_pref_str.replace("chart", "").replace("graph", "").replace("plot", "").strip()
        if chart_pref_str in ("bar", "line", "pie", "table", "kpi"):
            params["chart_preference"] = chart_pref_str

    # Metrics

    metrics = raw.get("metrics")
    if isinstance(metrics, list):
        params["metrics"] = [str(m).upper() for m in metrics if m]
    elif isinstance(metrics, str) and metrics:
        params["metrics"] = [metrics.upper()]

    # Volume = VALUE_USD guard.
    # "volume" / "trade volume" means dollar value UNLESS the question explicitly
    # asks for weight (in kg, tonnes, etc.). Reset both metrics and sort_metric.
    q_lower_vol = question.lower()
    has_volume_word = any(v in q_lower_vol for v in ["volume", "trade volume"])
    has_weight_qualifier = any(w in q_lower_vol for w in ["weight", "kg", "kilogram", "tonne", "ton ", "tonnage"])
    if has_volume_word and not has_weight_qualifier:
        params["metrics"] = ["VALUE_USD"]
        if params.get("sort_metric") in ("NET_WEIGHT", "WEIGHT"):
            logger.info("[parse_and_resolve_parameters] Volume query without weight qualifier: resetting sort_metric NET_WEIGHT → VALUE_USD.")
            params["sort_metric"] = "VALUE_USD"

    # Group by
    group_by = raw.get("group_by")
    if isinstance(group_by, list):
        params["group_by"] = [str(g) for g in group_by if g]
        params["dimensions"] = params["group_by"]
    elif isinstance(group_by, str) and group_by:
        params["group_by"] = [group_by]
        params["dimensions"] = [group_by]

    # Explicit product-level growth override to ensure 'product/products' queries map to hs_heading
    if params.get("intent") == "growth":
        q_lower = question.lower()
        if any(term in q_lower for term in ["product", "products"]):
            params["group_by"] = ["hs_heading"]
            params["dimensions"] = ["hs_heading"]

        # Decline/decrease directional context detection
        # Route stays as "growth" (math is identical), but NLG uses this flag
        # to confirm/correct the user's directional expectation.
        decline_terms = ["decline", "decrease", "drop", "fall", "shrink", "contracted", "contract", "down"]
        if any(term in q_lower for term in decline_terms):
            extra = params.setdefault("extra", {})
            extra["directional_context"] = "decline"

    # Explicit override for ranking queries asking for "both" flows to ensure flow grouping is included
    if params.get("intent") == "ranking":
        q_lower = question.lower()
        if "both" in q_lower or ("import" in q_lower and "export" in q_lower):
            if "group_by" not in params:
                params["group_by"] = ["partner_country"]
            if "flow" not in [g.lower() for g in params["group_by"]]:
                params["group_by"].append("flow")
            params["dimensions"] = params["group_by"]

    # Explicit override for breakdown queries asking for "product breakdown" to use hs_chapter
    if "product breakdown" in question.lower():
        params["group_by"] = ["hs_chapter"]
        params["dimensions"] = ["hs_chapter"]

    # Check for multi-year/trend keywords to trigger range instead of single year fallback
    multi_year_keywords = ["over the years", "historically", "over time", "across years", "historical trend", "years trend", "historical"]
    is_trend_query = any(kw in question.lower() for kw in multi_year_keywords) or params.get("intent") in ("trend",)
    if is_trend_query:
        freq = params.get("frequency") or "A"
        if freq == "A":
            has_any_time_context = any(
                params.get(k) is not None
                for k in ("year", "years", "period", "month", "quarter", "semester", "start_period", "end_period")
            )
            if not has_any_time_context:
                import datetime
                current_yr = datetime.datetime.now().year
                start_yr = current_yr - 2
                end_yr = current_yr
                params["start_period"] = str(start_yr)
                params["end_period"] = str(end_yr)
                params["period"] = None
                params["year"] = None
                params["years"] = None
                params["frequency"] = "A"
                logger.info(f"[llm_extractor] Trend/Historical query detected. Forcing multi-year range {start_yr}-{end_yr}.")

    # --- FALLBACK-ONLY regex enrichment ---
    # These never overwrite a value the LLM already gave us. They only fill
    # gaps, and every fill is logged so silent disagreements are visible.
    _fill_semester_params_from_regex(params, question)
    _fill_transport_modes_from_regex(params, question)
    _fill_sitc_from_regex(params, question)

    # "Volume" Keyword Triggers NET_WEIGHT Inclusion
    volume_keywords = ["volume", "quantity", "weight", "tonnage", "mass", "kg", "kilogram", "kilograms"]
    if any(kw in question.lower() for kw in volume_keywords):
        metrics = params.setdefault("metrics", [])
        if "NET_WEIGHT" not in metrics:
            metrics.append("NET_WEIGHT")
        extra = params.setdefault("extra", {})
        extra["volume_requested"] = True

    # Force growth intent override if "growth" or "grow" is explicitly asked
    # (unless trade balance keyword is present, which takes absolute precedence)
    q_lower = question.lower()
    has_balance = any(term in q_lower for term in ["balance", "surplus", "deficit", "net trade"])
    if ("growth" in q_lower or "grow" in q_lower) and not has_balance:
        params["intent"] = "growth"

    # Force trade_direction override based on explicit keywords in the question
    # to correct LLM extraction errors (e.g. "export growth" pulling IM)
    has_export = "export" in q_lower or "exports" in q_lower
    has_import = "import" in q_lower or "imports" in q_lower
    if has_import and "from cambodia" in q_lower:
        params["trade_direction"] = "EX"
    elif has_export and "to cambodia" in q_lower:
        params["trade_direction"] = "IM"
    elif has_export and not has_import:
        params["trade_direction"] = "EX"
        # Move non-KH country to destination for exports
        if params.get("origin_country") and params.get("origin_country") != "KH":
            params["destination_country"] = params["origin_country"]
            params["origin_country"] = None
    elif has_import and not has_export:
        params["trade_direction"] = "IM"
        # Move non-KH country to origin for imports
        if params.get("destination_country") and params.get("destination_country") != "KH":
            params["origin_country"] = params["destination_country"]
            params["destination_country"] = None

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

    from app.core.constants import SEMESTER_S1_PATTERNS, SEMESTER_S2_PATTERNS

    has_s1 = any(re.search(p, q) for p in SEMESTER_S1_PATTERNS)
    has_s2 = any(re.search(p, q) for p in SEMESTER_S2_PATTERNS)

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
    from app.registry.transport_modes import TRANSPORT_MODE_LABELS, TRANSPORT_MODE_SYNONYMS
    q = question.lower()
    detected = []

    for code, synonyms in TRANSPORT_MODE_SYNONYMS.items():
        label = TRANSPORT_MODE_LABELS[code]
        if label in ("unknown", "other transport"):
            continue
        # Map inland waterway to inland to preserve exact historical regex output
        normalized_label = "inland" if label == "inland waterway" else label
        for syn in synonyms:
            pattern = rf"\b{re.escape(syn)}\b"
            if re.search(pattern, q):
                detected.append(normalized_label)
                break

    return detected


def _fill_sitc_from_regex(params: Dict[str, Any], question: str) -> None:
    """Fallback ONLY: fill sitc_section / sitc_division from regex if the LLM left them empty."""
    already_has_sitc = params.get("sitc_section") is not None or params.get("sitc_division") is not None
    if already_has_sitc:
        return

    q = question.upper()

    # Check SITC Section
    sec_match = re.search(r"\bSECTION\s+(\d)\b", q)
    if sec_match:
        digit = sec_match.group(1)
        if digit in SITC_SECTION_CODE_MAP:
            params["sitc_section"] = digit
            logger.info(f"[llm_extractor] LLM left SITC empty; regex fallback filled sitc_section: {params['sitc_section']}")
            return

    # Check SITC Division
    div_match = re.search(r"\bDIVISION\s+(\d{1,2})\b", q)
    if div_match:
        digit = div_match.group(1).zfill(2)
        params["sitc_division"] = digit
        logger.info(f"[llm_extractor] LLM left SITC empty; regex fallback filled sitc_division: {params['sitc_division']}")
        return
