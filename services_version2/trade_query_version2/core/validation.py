"""Natural-language parameter extraction for trade_query.

Product-to-HS-code resolution is fetched live from the DAL metadata endpoint
(/v1/metadata/dataset/{dataset}), covering all HS chapters and headings tracked
by the dataset.  A local CSV is used as a last-resort fallback when the DAL is
unavailable.
"""

from __future__ import annotations

import csv
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import httpx as _httpx
except ImportError:  # pragma: no cover
    _httpx = None  # type: ignore[assignment]

from .exceptions import ValidationError

logger = logging.getLogger(__name__)

MIN_YEAR = 2000
MAX_YEAR = 2100

from .countries import COUNTRY_TO_CODE_MAP

TRANSPORT_KEYWORDS = {
    "air": "air",
    "airport": "air",
    "sea": "sea",
    "ocean": "sea",
    "port": "sea",
    "land": "land",
    "road": "land",
    "rail": "rail",
    "train": "rail",
    "inland": "inland",
    "waterway": "inland",
    "river": "inland",
    "postal": "postal",
    "post": "postal",
    "multimodal": "multimodal",
    "multi-modal": "multimodal",
    "fixed installation": "fixed",
    "fixed": "fixed",
}

DIRECTION_KEYWORDS = {
    "export": "EX",
    "exports": "EX",
    "import": "IM",
    "imports": "IM",
}

INTENT_PATTERNS = {
    "ranking": [
        r"\btop\s+\d+\b",
        r"\bbottom\s+\d+\b",
        r"\brank(?:s|ed|ing|ings)?\b",
        r"\bmost\b",
        r"\blargest\b",
        r"\blowest\b",
        r"\bsmallest\b",
        r"\bleast\b",
    ],
    "trend": [
        r"\bmonthly\b",
        r"\btrend(?:s|ed|ing)?\b",
        r"\bover\s+time\b",
        r"\beach\s+month\b",
        r"\bquarterly\b",
    ],
    "comparison": [
        r"\bcompare\b",
        r"\bcomparison\b",
        r"\bversus\b",
        r"\bvs\b",
        r"\bbetween\b",
    ],
    "breakdown": [
        r"\bbreakdown\b",
        r"\bby\s+hs\b",
        r"\bby\s+product\b",
        r"\bhs\s+code\b",
    ],
    "growth": [
        r"\bgrowth\b",
        r"\bexport\s+growth\b",
        r"\bimport\s+growth\b",
        r"\bincrease\b",
        r"\bdecline\b",
        r"\bchange\b",
    ],
    "trade_balance": [
        r"\btrade\s+balance\b",
        r"\bbalance\s+of\s+trade\b",
    ],
    "summary": [
        r"\btotal\b",
        r"\bsummary\b",
        r"\boverall\b",
        r"\bhow\s+much\b",
        r"\bwhat\s+is\b",
    ],
}


def validate_question(question: str) -> str:
    if not question or not isinstance(question, str):
        raise ValidationError("Question must be a non-empty string", field="question")
    question = question.strip()
    if len(question) < 5:
        raise ValidationError("Question must be at least 5 characters", field="question")
    return question


def _correct_perspective(params: dict[str, Any]) -> dict[str, Any]:
    # Normalize base country when it's the only country mentioned
    origin = params.get("origin_country")
    dest = params.get("destination_country")
    direction = params.get("trade_direction")
    if direction:
        direction = direction.upper()
        if direction == "IM" and origin == "KH" and not dest:
            params["origin_country"] = None
            params["destination_country"] = "KH"
            origin = None
            dest = "KH"
        elif direction == "EX" and dest == "KH" and not origin:
            params["destination_country"] = None
            params["origin_country"] = "KH"
            dest = None
            origin = "KH"

    # Flip check
    intent = params.get("intent", "summary")
    if direction and intent != "comparison":
        should_flip = False
        if direction == "EX":
            if (origin and origin.upper() != "KH") or (dest and dest.upper() == "KH"):
                should_flip = True
        elif direction == "IM":
            if (dest and dest.upper() != "KH") or (origin and origin.upper() == "KH"):
                should_flip = True
        if should_flip:
            params["trade_direction"] = "IM" if direction == "EX" else "EX"
            
    return params


def post_resolve_parameters(llm_params: dict[str, Any], question: str) -> dict[str, Any]:
    """Apply post-resolution rules to LLM-extracted parameters."""
    params = dict(llm_params)
    
    # Post-resolve HS code if LLM returned a product name or did not find one
    hs_code = params.get("hs_code")
    if hs_code:
        if not hs_code.isdigit():
            resolved_hs = _extract_hs_code(hs_code)
            if resolved_hs:
                params["hs_code"] = resolved_hs
            else:
                # Fallback to extracting from the original question
                resolved_hs = _extract_hs_code(question)
                if resolved_hs:
                    params["hs_code"] = resolved_hs
    else:
        resolved_hs = _extract_hs_code(question)
        if resolved_hs:
            params["hs_code"] = resolved_hs

    # Ensure Cambodian trade balance defaults are set
    if params.get("intent") == "trade_balance":
        origin = params.get("origin_country")
        dest = params.get("destination_country")
        if origin and not dest:
            params["origin_country"] = "KH"
            params["destination_country"] = origin
        elif dest and not origin:
            params["origin_country"] = "KH"
            
    return _correct_perspective(params)


def extract_parameters(question: str) -> dict[str, Any]:
    """Master extraction: detect intent + extract entities from NL question."""
    question = validate_question(question)
    logger.info(f"[extract_parameters] Question: {question}")

    # Try LLM parameter extraction first
    try:
        from .llm_extractor import extract_parameters_llm
        llm_params = extract_parameters_llm(question)
        if llm_params is not None:
            logger.info(f"[extract_parameters] LLM extracted successfully: {llm_params}")
            return post_resolve_parameters(llm_params, question)
    except Exception as e:
        logger.warning(f"[extract_parameters] LLM parameter extraction errored: {e}. Falling back to regex.")

    logger.info("[extract_parameters] Running regex parameter extraction fallback")
    params: dict[str, Any] = {}

    # Intent detection
    params["intent"] = _detect_intent(question)

    # Countries
    origin, destination = _extract_countries(question)
    params["origin_country"] = origin
    params["destination_country"] = destination

    # Year / month / quarter
    years = _extract_years(question)
    if years:
        if len(years) > 1:
            params["start_period"] = str(min(years))
            params["end_period"] = str(max(years))
        else:
            params["year"] = years[0]
        params["years"] = years

    month = _extract_month(question)
    if month:
        params["month"] = month

    quarter = _extract_quarter(question)
    if quarter:
        params["quarter"] = quarter

    frequency = _extract_frequency(question)
    if frequency:
        params["frequency"] = frequency

    # HS chapter
    hs_chapter = _extract_hs_chapter(question)
    if hs_chapter:
        params["hs_chapter"] = hs_chapter

    # HS code
    hs_code = _extract_hs_code(question)
    if hs_code:
        params["hs_code"] = hs_code

    # Transport mode
    transport = _extract_transport_mode(question)
    if transport:
        params["mode_of_transport"] = transport

    # Trade direction
    direction = _extract_trade_direction(question)
    if direction:
        params["trade_direction"] = direction

    # For trade_balance with a single country, assume Cambodia is the other party
    if params.get("intent") == "trade_balance":
        origin = params.get("origin_country")
        dest = params.get("destination_country")
        if origin and not dest:
            params["origin_country"] = "KH"
            params["destination_country"] = origin
        elif dest and not origin:
            params["origin_country"] = "KH"

    # Top-N / limit  (also captures "bottom N" → sets sort_order=asc)
    top_n, sort_order = _extract_top_n(question)
    if top_n:
        params["limit"] = top_n
    if sort_order:
        params["sort_order"] = sort_order

    # Sort metric/measure detection
    q_lower = question.lower()
    if "volume" in q_lower or "weight" in q_lower or "net weight" in q_lower or "netweight" in q_lower:
        params["sort_metric"] = "NET_WEIGHT"
    elif "quantity" in q_lower or "qty" in q_lower:
        params["sort_metric"] = "QUANTITY"

    # Group by
    group_by = _extract_group_by(question)
    if group_by:
        params["group_by"] = group_by
        params["dimensions"] = group_by

    logger.info(f"[extract_parameters] Extracted: {params}")
    return _correct_perspective(params)


def _detect_intent(question: str) -> str:
    """Score question against intent patterns and return best match."""
    scores: dict[str, int] = {}
    for intent, patterns in INTENT_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, question, re.IGNORECASE))
        if score:
            scores[intent] = score

    if not scores:
        return "summary"

    return max(scores, key=scores.get)


def _extract_countries(question: str) -> tuple[str | None, str | None]:
    """Extract up to two country references with preposition awareness.
    
    Checks if a country is preceded by 'to'/'into' (destination) or 'from'/'out of' (origin).
    """
    matches = []
    for pattern, code in COUNTRY_TO_CODE_MAP.items():
        for match in re.finditer(pattern, question, re.IGNORECASE):
            matches.append((match.start(), code, pattern))
            
    matches.sort(key=lambda x: x[0])
    
    deduped = []
    seen = set()
    for start, code, pattern in matches:
        if code not in seen:
            deduped.append((start, code, pattern))
            seen.add(code)
            
    if not deduped:
        return None, None
        
    origin = None
    destination = None
    unassigned = []
    
    for start, code, pattern in deduped:
        prefix = question[:start].rstrip().lower()
        if re.search(r"\b(to|into)\b\s*$", prefix):
            if not destination:
                destination = code
            else:
                unassigned.append(code)
        elif re.search(r"\b(from|out of)\b\s*$", prefix):
            if not origin:
                origin = code
            else:
                unassigned.append(code)
        else:
            unassigned.append(code)
            
    for code in unassigned:
        if not origin:
            origin = code
        elif not destination:
            destination = code
            
    return origin, destination



def _extract_years(question: str) -> list[int]:
    """Extract all 4-digit years, supporting relative year references like 'last year', 'this year', and 'last N years'."""
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", question)]
    
    import datetime
    current_year = datetime.datetime.now().year
    
    q_lower = question.lower()
    
    # Check for relative year ranges like "last 3 years" or "past 5 years" or "previous 3 years"
    match = re.search(r"\b(?:last|past|previous)\s+(\d+)\s+years?\b", q_lower)
    if match:
        num_years = int(match.group(1))
        # Generate the last N years including the current year
        for i in range(num_years):
            years.append(current_year - i)
    else:
        if "last year" in q_lower or "previous year" in q_lower:
            years.append(current_year - 1)
        elif "this year" in q_lower or "current year" in q_lower:
            years.append(current_year)
        elif "next year" in q_lower:
            years.append(current_year + 1)
        
    return sorted(list(set(y for y in years if MIN_YEAR <= y <= MAX_YEAR)))


def _extract_month(question: str) -> int | None:
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    for name, num in months.items():
        if re.search(rf"\b{name}\b", question, re.IGNORECASE):
            return num
    return None


def _extract_quarter(question: str) -> str | None:
    match = re.search(r"\b(q[1-4])\b", question, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def _extract_frequency(question: str) -> str | None:
    q_lower = question.lower()
    if "monthly" in q_lower or "each month" in q_lower or "every month" in q_lower:
        return "M"
    if "quarterly" in q_lower or "each quarter" in q_lower or "every quarter" in q_lower:
        return "Q"
    if "yearly" in q_lower or "annual" in q_lower or "annually" in q_lower or "each year" in q_lower:
        return "A"
    return None


def _extract_hs_chapter(question: str) -> str | None:
    """Extract HS chapter (2 digits) if preceded by 'chapter' or 'ch'."""
    match = re.search(r"\b(?:chapter|ch|hs\s+chapter)\s+(\d{1,2})\b", question, re.IGNORECASE)
    if match:
        return match.group(1).zfill(2)
    return None


_PRODUCT_KEYWORD_MAP: dict[str, str] | None = None

# Stop-words that are too generic to use as product keywords
_LABEL_STOP_WORDS = frozenset({
    # Generic descriptors
    "other", "live", "fresh", "chilled", "frozen", "dried", "salted", "smoked",
    "parts", "preparations", "products", "articles", "goods", "materials",
    "thereof", "such", "including", "excluding", "similar", "related",
    "miscellaneous", "various", "special", "general", "certain", "edible",
    # Prepositions / conjunctions / pronouns (must not be indexed as products)
    "from", "with", "into", "onto", "upon", "within", "without", "between",
    "through", "during", "before", "after", "above", "below", "under",
    "over", "near", "about", "along", "across", "against", "among",
    "and", "but", "nor", "for", "yet", "both", "either", "neither",
    "not", "only", "whether", "that", "this", "these", "those",
    "the", "its", "their", "which", "when", "where", "who", "whom",
    # Common verbs in HS descriptions
    "designed", "used", "fitted", "made", "derived", "obtained", "produced",
    "rendered", "processed", "refined", "treated", "mixed", "combined",
    # Short generic words
    "type", "form", "kind", "sort", "item", "unit", "piece", "set",
    "base", "pure", "raw", "new", "old", "used", "waste", "scrap",
    # Quantifiers & query terms
    "all", "any", "every", "each", "some", "few", "many", "several",
    "import", "imports", "export", "exports", "trade", "volume", "value",
    "values", "summary", "overall", "show", "give", "find", "get", "list",
    # Transport / routing terms (avoid collision with transport modes)
    "air", "sea", "land", "rail", "road", "port", "airport", "via", "by",
    "freight", "cargo", "transport",
})



def _build_terms_from_label(label: str) -> list[str]:
    """Split an HS label into indexable keyword terms.

    Strategy:
    - Only index the FIRST comma/semicolon-delimited segment as the primary
      identifier.  This prevents compound headings like
      'Polishes, creams ... for footwear, furniture' from falsely mapping
      'footwear' or 'furniture' to the polish heading.
    - After extracting the first segment, also emit each significant single
      word in that segment (e.g. 'coffee, tea' -> ['coffee', 'tea']).
    - Phrases following 'for', 'of', 'not', 'whether' inside the first
      segment are stripped to avoid mapping scope qualifiers as product names.
    """
    label = label.strip().rstrip(".\n\r").lower()

    # Take only the first major segment (before a comma or semicolon)
    first_segment = re.split(r"[,;]", label)[0].strip()

    # Strip scope qualifiers: "polishes for footwear" -> "polishes"
    first_segment = re.split(r"\bfor\b|\bof\b|\bnot\b|\bwhether\b|\bexcluding\b", first_segment)[0].strip()

    terms: list[str] = []

    # Emit the full first segment as a phrase (if not a stop-word and reasonably short)
    cleaned = first_segment.rstrip(".").strip()
    if 2 <= len(cleaned) <= 40 and cleaned not in _LABEL_STOP_WORDS:
        terms.append(cleaned)

    # Also split the first segment on 'and' to emit sub-terms
    for part in re.split(r"\band\b", first_segment):
        word_phrase = part.strip().rstrip(".").strip()
        if 2 <= len(word_phrase) <= 40 and word_phrase not in _LABEL_STOP_WORDS:
            if word_phrase not in terms:
                terms.append(word_phrase)
        # Individual words within this part
        for word in word_phrase.split():
            word = word.strip().rstrip(".")
            if len(word) >= 3 and word not in _LABEL_STOP_WORDS and word not in terms:
                terms.append(word)

    return list(dict.fromkeys(terms))  # deduplicate while preserving order


def _get_product_keyword_map() -> dict[str, str]:
    """Return a mapping of lowercase product keyword → HS heading/chapter code.

    Resolution order:
    1. Live fetch from the DAL metadata endpoint (HS_CHAPTER + HS_HEADING).
    2. Fallback: parse the local ``hs_code.csv`` file.
    3. Hard-coded minimal defaults (retained for extreme offline scenarios).

    Results are cached in-process after the first call.
    """
    global _PRODUCT_KEYWORD_MAP
    if _PRODUCT_KEYWORD_MAP is not None:
        return _PRODUCT_KEYWORD_MAP

    mapping: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # 1. Fetch live from the DAL metadata endpoint                         #
    # ------------------------------------------------------------------ #
    dal_base = os.getenv("DAL_BASE_URL", "http://172.25.3.243:8989").rstrip("/")
    dal_api_key = os.getenv("DAL_API_KEY", "dal-pub-key-abc123xyz789")
    dal_dataset = os.getenv("DAL_DATASET_CODE", "trade_volume")
    metadata_url = f"{dal_base}/v1/metadata/dataset/{dal_dataset}"

    try:
        if _httpx is None:
            raise ImportError("httpx not available")
        resp = _httpx.get(
            metadata_url,
            headers={"Accept": "application/json", "x-api-key": dal_api_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        meta = resp.json()

        # Walk through every dimension; collect HS_CHAPTER and HS_HEADING entries.
        # HS_HEADING codes are 4 digits (higher precision) → stored first.
        # HS_CHAPTER codes are 2 digits (lower precision) → stored only when no
        # heading-level code is already registered for that keyword.
        hs_heading_entries: list[tuple[str, str]] = []
        hs_chapter_entries: list[tuple[str, str]] = []

        for dim in meta.get("dimensions", []):
            dim_code = dim.get("code", "")
            data = dim.get("data", [])
            if dim_code == "HS_HEADING":
                for entry in data:
                    code = str(entry.get("code", "")).strip()
                    label = str(entry.get("label", "")).strip()
                    for term in _build_terms_from_label(label):
                        hs_heading_entries.append((term, code))
            elif dim_code == "HS_CHAPTER":
                for entry in data:
                    code = str(entry.get("code", "")).strip()
                    label = str(entry.get("label", "")).strip()
                    for term in _build_terms_from_label(label):
                        hs_chapter_entries.append((term, code))

        # Register heading-level codes first (more specific)
        for term, code in hs_heading_entries:
            if term not in mapping:
                mapping[term] = code

        # Then chapter-level codes (only if term not yet registered)
        for term, code in hs_chapter_entries:
            if term not in mapping:
                mapping[term] = code

        logger.info(
            f"[_get_product_keyword_map] Loaded {len(mapping)} product terms "
            f"from DAL metadata ({metadata_url})"
        )

    except Exception as exc:
        logger.warning(
            f"[_get_product_keyword_map] Could not fetch DAL metadata ({metadata_url}): {exc}. "
            "Falling back to local CSV."
        )

    # ------------------------------------------------------------------ #
    # 2. Fallback: parse local hs_code.csv                                #
    # ------------------------------------------------------------------ #
    if not mapping:
        csv_path = Path("data/processed/structured/hs_code.csv")
        if not csv_path.exists():
            csv_path = (
                Path(__file__).resolve().parents[3]
                / "data" / "processed" / "structured" / "hs_code.csv"
            )
        if csv_path.exists():
            try:
                with open(csv_path, mode="r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        hs_code = row.get("hs_code", "")
                        desc = row.get("description", "")
                        if len(hs_code) >= 4:
                            heading_code = hs_code.replace(".", "")[:4]
                            for term in _build_terms_from_label(desc.split(">")[0]):
                                if term not in mapping:
                                    mapping[term] = heading_code
                logger.info(
                    f"[_get_product_keyword_map] Loaded {len(mapping)} product terms from local CSV."
                )
            except Exception as e:
                logger.warning(f"[_get_product_keyword_map] Failed to load local CSV: {e}")

    # These are canonical aliases — always override whatever the DAL registered,
    # because the DAL may map common words to non-canonical headings via compound labels.
    _MINIMAL_DEFAULTS: dict[str, str] = {
        # Agricultural / food
        "rice": "1006",
        "wheat": "1001",
        "corn": "1005",
        "maize": "1005",
        "cement": "2523",
        "coal": "2701",
        "petroleum": "2709",
        # Common product aliases not in DAL HS labels verbatim
        "beef": "0201",          # "Meat of bovine animals, fresh or chilled."
        "pork": "0203",          # "Meat of swine"
        "chicken": "0207",       # "Meat and edible offal, of poultry"
        "milk": "0401",          # "Milk and cream"
        "butter": "0405",        # "Butter and other fats derived from milk"
        "rubber": "4001",        # "Natural rubber" (not chemical preparations)
        "wool": "5101",          # "Wool, not carded or combed" (not lanolin/grease)
        "steel": "7208",         # "Flat-rolled products of iron/non-alloy steel"
        "iron": "7208",
        "copper": "7403",        # "Refined copper"
        "gold": "7108",          # "Gold (including gold plated with platinum)"
        "silver": "7106",        # "Silver, unwrought or semi-manufactured"
        "platinum": "7110",      # "Platinum, unwrought or semi-manufactured"
        "car": "8703",           # "Motor cars"
        "cars": "8703",
        "automobile": "8703",
        "automobiles": "8703",
        "motorcycle": "8711",    # "Motorcycles (including mopeds)"
        "motorcycles": "8711",
        "moped": "8711",
        "computer": "8471",      # "Automatic data processing machines"
        "computers": "8471",
        "laptop": "8471",
        "laptops": "8471",
        "aircraft": "8802",      # "Other aircraft (helicopters, aeroplanes)"
        "airplane": "8802",
        "aeroplane": "8802",
        "helicopter": "8802",
        "phone": "8517",         # "Telephone sets"
        "phones": "8517",
        "smartphone": "8517",
        "smartphones": "8517",
        "mobile": "8517",
        "electronics": "8517",
        "toys": "9503",          # "Tricycles, scooters, pedal cars..."
    }

    # Always override: these canonical aliases take precedence over DAL labels
    mapping.update(_MINIMAL_DEFAULTS)



    _PRODUCT_KEYWORD_MAP = mapping
    return _PRODUCT_KEYWORD_MAP



def _extract_hs_code(question: str) -> str | None:
    """Extract HS code or heading (4 to 8 digits) or resolve product name dynamically.

    HS codes are only extracted when explicitly tagged in the query
    (e.g. 'HS 8471', 'code 2709', 'heading 1006').  Bare digit sequences
    are NOT auto-matched to avoid false positives with years, quantities, etc.

    Product names are resolved dynamically via the DAL metadata keyword map.
    """
    # 1. Explicitly tagged HS codes ('HS 8471', 'HS code 2709', 'heading 1006')
    match = re.search(r"\b(?:heading|code|hs|hs\s+code)\s+(\d{4,8})\b", question, re.IGNORECASE)
    if match:
        return match.group(1)

    # 2. Dynamic product keyword mapping resolved from DAL metadata
    q_lower = question.lower()
    product_map = _get_product_keyword_map()

    # Match longest phrase keys first to prevent partial/sub-string conflicts
    for key in sorted(product_map.keys(), key=len, reverse=True):
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, q_lower):
            return product_map[key]

    return None



def _extract_transport_mode(question: str) -> str | None:
    for keyword, mode in TRANSPORT_KEYWORDS.items():
        if re.search(rf"\b{keyword}\b", question, re.IGNORECASE):
            return mode
    return None


def _extract_trade_direction(question: str) -> str | None:
    """Determine Cambodia's trade direction (EX or IM) from the question.

    Key insight: the grammatical subject of import/export matters.

    Examples:
      - "Which countries import the most Cambodian rice?"
          → partner countries are importing FROM Cambodia → Cambodia EXports → EX
      - "Who exports goods to Cambodia?"
          → someone exports TO Cambodia → Cambodia IMports → IM
      - "Show me Cambodia's exports to China"
          → Cambodia exports → EX
      - "What did Cambodia import from Thailand?"
          → Cambodia imports → IM
    """
    q = question.lower()

    # --- Perspective-aware patterns (checked before simple keyword scan) ---

    # Pattern: "partner countries / who / which countries ... import ... Cambodian ..."
    # → The partner is doing the importing FROM Cambodia → Cambodia EXports
    cambodian_export_patterns = [
        r"\b(?:partner\s+countries?|which\s+countries?|who|what\s+countries?)\b.{0,60}\b(?:import|buy|purchase|receive)\b",
        r"\b(?:import|buy|purchase)\b.{0,40}\bcambodian\b",
        r"\bcambodian\b.{0,40}\bexport(?:ed|s)?\b",
        r"\bexport(?:ed|s|ing)?\b.{0,40}\bfrom\s+cambodia\b",
        r"\bcambodia(?:n)?\b.{0,30}\bexport(?:ed|s|ing)?\b",
        r"\bwho\s+(?:are|is)\s+(?:the\s+)?(?:top\s+)?(?:buyers?|importers?|purchasers?)\b",
    ]
    for pattern in cambodian_export_patterns:
        if re.search(pattern, q, re.IGNORECASE):
            return "EX"

    # Pattern: "what does Cambodia import", "Cambodia's imports", "imported by Cambodia"
    # → Cambodia is the one importing → IM
    cambodian_import_patterns = [
        r"\bcambodia(?:n)?\b.{0,30}\bimport(?:ed|s|ing)?\b",
        r"\bimport(?:ed|s|ing)?\b.{0,40}\b(?:by|into)\s+cambodia\b",
        r"\bimport(?:ed|s|ing)?\b.{0,40}\bfrom\b",  # "imports from X" = KH imports
        r"\bcambodia\b.{0,30}\breceive(?:d|s|ing)?\b",
    ]
    for pattern in cambodian_import_patterns:
        if re.search(pattern, q, re.IGNORECASE):
            return "IM"

    # --- Fallback: simple keyword scan ---
    for keyword, code in DIRECTION_KEYWORDS.items():
        if re.search(rf"\b{keyword}\b", question, re.IGNORECASE):
            return code

    return None



def _extract_top_n(question: str) -> tuple[int | None, str | None]:
    """Extract the N in 'top N' or 'bottom N', and the implied sort order.

    Returns:
        (n, sort_order) where sort_order is 'asc' for 'bottom N', 'desc' for
        'top N', and None when no N is found.
    """
    # "top N" → descending (largest first)
    match = re.search(r"\btop\s+(\d+)\b", question, re.IGNORECASE)
    if match:
        return int(match.group(1)), "desc"

    # "bottom N" / "lowest N" / "smallest N" / "least N" → ascending (smallest first)
    match = re.search(
        r"\b(?:bottom|lowest|smallest|least)\s+(\d+)\b", question, re.IGNORECASE
    )
    if match:
        return int(match.group(1)), "asc"

    return None, None


def _extract_group_by(question: str) -> list[str] | None:
    """Detect if the question specifies grouping dimensions (e.g. 'by HS chapter', 'by transport mode')."""
    q_lower = question.lower()

    # Check transport mode
    if any(phrase in q_lower for phrase in ["mode of transport", "transport mode", "transport modes", "by transport"]):
        return ["mode_of_transport"]

    # Check HS chapter
    if any(phrase in q_lower for phrase in ["by hs chapter", "by chapter", "by chapters", "hs chapters", "by hs chapters"]):
        return ["hs_chapter"]

    # Check HS heading
    if any(phrase in q_lower for phrase in ["by hs heading", "by heading", "by headings", "hs headings"]):
        return ["hs_heading"]

    # Check HS code
    if any(phrase in q_lower for phrase in ["by hs code", "by product", "by products", "hs codes", "by hs codes"]):
        return ["hs_code"]

    # Check partner country — both "by partner" AND bare "partner countries" / "countries"
    if any(phrase in q_lower for phrase in [
        "by country", "by partner", "by partners", "trading partners",
        "partner countries", "partner country",
        "which countries", "what countries", "who are the",
    ]):
        return ["partner_country"]

    # Check flow / direction
    if any(phrase in q_lower for phrase in ["by flow", "by trade direction", "by direction"]):
        return ["flow"]

    return None
