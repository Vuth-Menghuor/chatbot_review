"""
Entity and subject-extraction utilities for the orchestrator service.

Contains functions that identify or isolate the product/subject entity
within a user query — as opposed to text_utils.py, which only reformats
text without interpreting query intent.

NOTE: extract_entity() and clean_hs_query_for_retrieval() maintain separate
prefix-stripping regex lists that overlap significantly (HS-code phrasing,
"classify", etc.). They're kept independent here because they serve
different callers with different strictness needs:
  - extract_entity: session-state entity tracking, also strips stopwords
    and conversational fragments ("what about", "and for")
  - clean_hs_query_for_retrieval: retrieval-query cleaning, preserves
    casing/technical detail, no stopword removal
If these are ever meant to converge, consider factoring the shared
HS-prefix patterns into a single constant both functions pull from.
"""

import re
from typing import Optional

# Shared HS-code prefix patterns used by both extract_entity() and clean_hs_query_for_retrieval()
_HS_PREFIX_PATTERNS: list[str] = [
    r"^(?:what(?:'?s|\s+is)?(?:\s+the)?\s+)?hs\s*(?:code|codes|number|tariff)?\s*(?:of|for|on|about)?\s*",
    r"^(?:find|get|look\s+up|give\s+me|tell\s+me|show)(?:\s+the)?\s+hs\s*(?:code|codes|number|tariff)?\s*(?:of|for|on|about)?\s*",
    r"^classify(?:\s+the)?\s*(?:product)?\s*",
    r"^(?:please\s+)?(?:tell\s+me\s+)?how\s+to\s+classify\s*",
]


def extract_entity(query: str) -> Optional[str]:
    """
    Extract the core subject entity (noun phrase) from a user query.

    This is a **stateless utility** used by:
    - Session-state writer: to populate ``SessionContext.last_entity`` after
      each processed turn.
    - ``ServiceCoordinator._merge_pending_with_clarification``: to fall back
      to the turn-1 entity when the turn-2 fragment carries no entity of its
      own.

    Strategy:
    1. Strip trailing punctuation first so that pure-filler fragments like
       "and for?" or "for?" match their prefix patterns cleanly.
    2. Iteratively strip well-known intent-keyword prefixes ("hs code of",
       "trade data for", "calculate import duty for", etc.) until only the
       product / subject noun phrase remains.
    3. Strip any residual trailing punctuation.
    4. Remove obvious stopwords.
    5. Return ``None`` if nothing meaningful survives.

    Args:
        query: Raw or normalised user query string.

    Returns:
        Lowercase entity string (e.g. ``"car"``, ``"boat"``, ``"rice"``),
        or ``None`` if extraction yields nothing usable.
    """
    if not query or not query.strip():
        return None

    # Step 0: Try using LLM to do the extraction first, with regex as a fallback
    try:
        from app.ai import get_llm_service
        from prompts.dynamic_prompt_manager import DynamicPromptManager
        llm = get_llm_service()
        if llm.is_available():
            provider = llm.router.providers.get("gemini")
            if provider and provider.is_available():
                if '_prompt_manager_cached' not in globals():
                    globals()['_prompt_manager_cached'] = DynamicPromptManager()
                prompt_manager = globals()['_prompt_manager_cached']
                prompt = prompt_manager.render(
                    "extract_entity_llm",
                    query=query
                )
                response = provider.client.models.generate_content(
                    model=provider.model_name,
                    contents=prompt
                )
                text_extracted = (response.text or "").strip().lower()
                # Clean up any verbose prefix the model might prepend
                text_extracted = re.sub(r"^(?:product name|the product name|commodity name|extracted entity|entity|extracted product|product)\s*(?:is)?\s*[:=-]?\s*", "", text_extracted).strip()
                text_extracted = text_extracted.strip("'\"` ")
                if text_extracted in ("none", "null", "empty", "n/a", ""):
                    return None
                if text_extracted and len(text_extracted) > 1:
                    return text_extracted
    except Exception as e:
        # Fall back to regex on any error
        pass

    text = query.strip().lower()

    """
    Step 1: Strip trailing punctuation FIRST so that pure-filler
    fragments like "and for?" match the prefix patterns below.
    The prefix patterns require the keyword to be followed by whitespace
    or end-of-string; removing trailing '?' here enables them to fire.
    """

    text = re.sub(r"[?!.,;:]+$", "", text).strip()
    if not text:
        return None

    # Chained prefixes collapse on repeated passes.
    PREFIXES = [
        # Conversational openers — e.g. "hi", "hello", "hey", "excuse me"
        r"^(?:hi|hello|hey|excuse\s+me)\s*[,!]?\s*",
        # Polite filler + calculation starters — e.g. "how much tax if i import a"
        r"^(?:how\s+much\s+(?:tax|duty|tariff|vat|fee)\s+if\s+i\s+import\s+(?:a\s+)?)",
        r"^(?:how\s+much\s+(?:is|are|would|does)?\s*(?:the\s+)?(?:tax|duty|tariff|fee|vat)?\s*(?:if\s+i\s+import\s+(?:a\s+)?)?)",
        # Trade-query signals
        r"^(?:what(?:'?s|\s+is)?(?:\s+the)?\s+)?trade\s+(?:data|statistics|volume|flow|flows)?\s*(?:of|for|on|about)?\s*",
        r"^(?:import|export)\s+(?:data|statistics|volume|flow)?\s*(?:of|for|on|from|to)?\s*",
        # Calculation signals
        r"^(?:calculate|compute|how\s+much\s+(?:is|are|does)?)\s+(?:the\s+)?(?:import\s+)?(?:duty|tax|tariff|vat|fee)?\s*(?:of|for|on)?\s*",
        r"^(?:i\s+)?(?:need|want)\s+(?:a\s+)?(?:tax|duty|tariff|vat|import\s+tax)?\s*(?:calc|calculation|calculator)?\s*(?:for|on|of)?\s*",
        r"^(?:can\s+(?:you|u)|could\s+you|please|pls)\s+(?:calc|calculate|compute|tell\s+me|help\s+me\s+calculate)?\s+(?:the\s+)?(?:import\s+)?(?:tax|duty|tariff|vat|fee)?\s*(?:for|on|of)?\s*",
        r"^(?:can\s+(?:you|u)|could\s+you)\s+(?:calc|calculate|compute|help|show|find|get)?\s*",
        r"^(?:tax|duty|tariff|import\s+tax)\s+(?:calc|calculation|calculator)\s+(?:for|on|of)?\s*",
        r"^(?:import|export)\s+(?:duty|tax|tariff|fee)\s+(?:of|for|on)?\s*",
        r"^what(?:'?s|\s+is)\s+(?:the\s+)?(?:import|export)?\s+(?:duty|tax|tariff)\s+(?:for|on)?\s*",
        # General / definition signals
        r"^(?:what(?:'?s|\s+is)|define|explain|describe|tell\s+me\s+about|how\s+to)\s+",
        # Generic question starters
        r"^(?:about|regarding|re:?)\s+",
        # Conversational fragment starters ("what about X", "and for X", "for X")
        r"^(?:what|how)\s+about\s+",
        r"^and\s+for\s+",
        r"^and\s+for$",        # handles "and for" (after trailing punctuation stripped)
        r"^for\s+",
        r"^for$",              # handles standalone "for" (after trailing punctuation stripped)
        # Action-verb starters that precede the actual product entity:
        # e.g. "importing GTR sport car" → "GTR sport car"
        #      "exporting laptop components" → "laptop components"
        r"^(?:importing|exporting|import|export)\s+(?:tax|duty|tariff|vat|fee)?\s*(?:pls|please)?\s*",
        r"^(?:pls|please)\s+",
        # Action-verb + article starters — e.g. "import a", "import the"
        r"^(?:import|export)\s+(?:a|an|the)\s+",
        # HS-related action starters that survive earlier pattern runs
        r"^(?:check|look\s+up|search|find|get)\s+(?:hs\s+code\s+(?:for|of)\s+)?\s*",
    ] + _HS_PREFIX_PATTERNS

    changed = True
    while changed:
        changed = False
        for prefix_pattern in PREFIXES:
            new_text = re.sub(prefix_pattern, "", text, flags=re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                changed = True
                break  # restart loop so earlier patterns re-run

    # Step 3: Strip inline/standalone HS codes that survived prefix removal
    # e.g. "car hs 8703.22.00" → "car", "8703.24.00, cif..." → "cif..."
    text = re.sub(r"^(?:\s*hs\s*(?:code\s*)?)?\d{4}\.\d{2}(?:\.\d{2})?[,\s]*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\bhs\s*(?:code\s*)?\d{4}\.\d{2}(?:\.\d{2})?[,\s]*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+\d{4}\.\d{2}(?:\.\d{2})?", "", text).strip()
    # Strip standalone monetary/price tokens (e.g. $10000, 10000$, 10000 USD)
    money_pat = (
        r"[\$\€\£\¥៛]\s*\d+(?:,\d{3})*(?:\.\d+)?"
        r"|\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:usd|khr|thb|eur|gbp|cny|jpy|vnd|sgd|myr|dollars|riel|riels|baht|yuan|rmb|yen|[\$\€\£\¥៛])?"
    )
    text = re.sub(money_pat, "", text, flags=re.IGNORECASE).strip()

    # Strip leftover standalone currency symbols
    text = re.sub(r"[\$\€\£\¥៛]", "", text).strip()

    # Strip raw digits of length 4 to 8 (potential raw HS codes)
    text = re.sub(r"\b\d{4,8}\b", "", text).strip()

    # Step 4: Strip trailing key=value parameters (cif is $..., dv=..., cif=..., dq ...)
    # e.g. "car cif is $10500 from china acfta rate dv=0" → "car"
    text = re.sub(r"\s+(?:hs|cif|fob|dv|dq|acfta|atiga|rcep|from|rate|origin)[\s=:][^,]+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"[,;\s]*cif\s*(?:is\s*)?\$?\d[\d,.]*(?:\s*(?:usd|khr|dollars|eur|cif))?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"[,;\s]*(?:importing\s+)?from\s+[a-z]+(?:\s+[a-z]+)?", "", text, flags=re.IGNORECASE).strip()

    # Step 5: Strip any residual trailing punctuation
    text = re.sub(r"[?!.,;:]+$", "", text).strip()

    # Step 6: Remove obvious stopwords that survived stripping
    STOPWORDS = {
        "a", "an", "the", "its", "it", "that", "this", "these", "those", "some",
        "importing", "exporting", "code", "use", "using", "try", "correct", "right",
        "i", "we", "you", "he", "she", "they", "paid", "bought", "cost", "pay", "buy",
        "worth", "value", "valued", "hs"
    }
    words = text.split()
    words = [w for w in words if w not in STOPWORDS]
    text = " ".join(words).strip()

    # Return None when nothing meaningful is left (empty or single char)
    if not text or len(text) <= 1:
        return None

    return text

_MONEY_PATTERN = re.compile(
    r"[\$\€\£\¥៛]\s*(\d+(?:,\d{3})*(?:\.\d+)?)"
    r"|(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:usd|khr|thb|eur|gbp|cny|jpy|vnd|sgd|myr|dollars|riel|riels|baht|yuan|rmb|yen)\b",
    re.IGNORECASE,
)

def extract_money_value(query: str) -> Optional[float]:
    """Extract a standalone monetary amount from a query — used to detect
    whether a turn answers a pending 'declared value' clarification."""
    if not query or not query.strip():
        return None
    match = _MONEY_PATTERN.search(query)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def clean_hs_query_for_retrieval(query: str) -> str:
    """
    Strips common prefix phrases related to HS code requests, leaving only
    the commercial or product description. Preserves casing and technical details.
    """
    if not query:
        return ""

    text = query.strip()
    prefix_stripped = False
    changed = True
    while changed:
        changed = False
        for pattern in _HS_PREFIX_PATTERNS:
            new_text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                changed = True
                prefix_stripped = True
                break

    text = re.sub(r"^[?.,\s]+", "", text)
    text = re.sub(r"[?.,\s]+$", "", text)

    # Only strip leftovers if a prefix pattern actually matched and stripped something
    if prefix_stripped:
        text = re.sub(r"^(?:and|or|but|with|for)\s+", "", text, flags=re.IGNORECASE).strip()

    return text if text else query


_ISO_COUNTRY_CODES = {
    "AF", "AX", "AL", "DZ", "AS", "AD", "AO", "AI", "AQ", "AG", "AR", "AM", "AW", "AU", "AT", "AZ",
    "BS", "BH", "BD", "BB", "BY", "BE", "BZ", "BJ", "BM", "BT", "BO", "BQ", "BA", "BW", "BV", "BR",
    "IO", "BN", "BG", "BF", "BI", "CV", "KH", "CM", "CA", "KY", "CF", "TD", "CL", "CN", "CX", "CC",
    "CO", "KM", "CD", "CG", "CK", "CR", "CI", "HR", "CU", "CW", "CY", "CZ", "DK", "DJ", "DM", "DO",
    "EC", "EG", "SV", "GQ", "ER", "EE", "SZ", "ET", "FK", "FO", "FJ", "FI", "FR", "GF", "PF", "TF",
    "GA", "GM", "GE", "DE", "GH", "GI", "GR", "GL", "GD", "GP", "GU", "GT", "GG", "GN", "GW", "GY",
    "HT", "HM", "VA", "HN", "HK", "HU", "IS", "IN", "ID", "IR", "IQ", "IE", "IM", "IL", "IT", "JM",
    "JP", "JE", "JO", "KZ", "KE", "KI", "KP", "KR", "KW", "KG", "LA", "LV", "LB", "LS", "LR", "LY",
    "LI", "LT", "LU", "MO", "MG", "MW", "MY", "MV", "ML", "MT", "MH", "MQ", "MR", "MU", "YT", "MX",
    "FM", "MD", "MC", "MN", "ME", "MS", "MA", "MZ", "MM", "NA", "NR", "NP", "NL", "NC", "NZ", "NI",
    "NE", "NG", "NU", "NF", "MP", "NO", "OM", "PK", "PW", "PS", "PA", "PG", "PY", "PE", "PH", "PN",
    "PL", "PT", "PR", "QA", "RE", "RO", "RU", "RW", "BL", "SH", "KN", "LC", "MF", "PM", "VC", "WS",
    "SM", "ST", "SA", "SN", "RS", "SC", "SL", "SG", "SX", "SK", "SI", "SB", "SO", "ZA", "GS", "SS",
    "ES", "LK", "SD", "SR", "SJ", "SE", "CH", "SY", "TW", "TJ", "TZ", "TH", "TL", "TG", "TK", "TO",
    "TT", "TN", "TR", "TM", "TC", "TV", "UG", "UA", "AE", "GB", "UM", "US", "UY", "UZ", "VU", "VE",
    "VN", "VG", "VI", "WF", "EH", "YE", "ZM", "ZW"
}

_COUNTRY_NAMES = {
    "afghanistan", "aland islands", "albania", "algeria", "american samoa", "andorra", "angola",
    "anguilla", "antarctica", "antigua and barbuda", "argentina", "armenia", "aruba", "australia",
    "austria", "azerbaijan", "bahamas", "bahrain", "bangladesh", "barbados", "belarus", "belgium",
    "belize", "benin", "bermuda", "bhutan", "bolivia", "bonaire", "bosnia and herzegovina",
    "botswana", "bouvet island", "brazil", "british indian ocean territory", "brunei", "brunei darussalam",
    "bulgaria", "burkina faso", "burundi", "cabo verde", "cambodia", "cameroon", "canada", "cayman islands",
    "central african republic", "chad", "chile", "china", "christmas island", "cocos islands",
    "colombia", "comoros", "congo", "cook islands", "costa rica", "cote d'ivoire", "croatia",
    "cuba", "curacao", "cyprus", "czechia", "czech republic", "denmark", "djibouti", "dominica", "dominican republic",
    "ecuador", "egypt", "el salvador", "equatorial guinea", "eritrea", "estonia", "eswatini",
    "ethiopia", "falkland islands", "faroe islands", "fiji", "finland", "france", "french guiana",
    "french polynesia", "french southern territories", "gabon", "gambia", "georgia", "germany",
    "ghana", "gibraltar", "greece", "greenland", "grenada", "guadeloupe", "guam", "guatemala",
    "guernsey", "guinea", "guinea-bissau", "guyana", "haiti", "heard island and mcdonald islands",
    "holy see", "honduras", "hong kong", "hungary", "iceland", "india", "indonesia", "iran",
    "iraq", "ireland", "isle of man", "israel", "italy", "jamaica", "japan", "jersey", "jordan",
    "kazakhstan", "kenya", "kiribati", "north korea", "south korea", "korea", "kuwait", "kyrgyzstan",
    "laos", "lao", "latvia", "lebanon", "lesotho", "liberia", "libya", "liechtenstein", "lithuania",
    "luxembourg", "macao", "madagascar", "malawi", "malaysia", "maldives", "mali", "malta",
    "marshall islands", "martinique", "mauritania", "mauritius", "mayotte", "mexico", "micronesia",
    "moldova", "monaco", "mongolia", "montenegro", "montserrat", "morocco", "mozambique", "myanmar",
    "namibia", "nauru", "nepal", "netherlands", "new caledonia", "new zealand", "nicaragua",
    "niger", "nigeria", "niue", "norfolk island", "northern mariana islands", "norway", "oman",
    "pakistan", "palau", "palestine", "panama", "papua new guinea", "paraguay", "peru", "philippines",
    "pitcairn", "poland", "portugal", "puerto rico", "qatar", "reunion", "romania", "russia",
    "russian federation", "rwanda", "saint barthelemy", "saint helena", "saint kitts and nevis",
    "saint lucia", "saint martin", "saint pierre and miquelon", "saint vincent and the grenadines",
    "samoa", "san marino", "sao tome and principe", "saudi arabia", "senegal", "serbia", "seychelles",
    "sierra leone", "singapore", "sint maarten", "slovakia", "slovenia", "solomon islands", "somalia",
    "south africa", "south georgia and the south sandwich islands", "south sudan", "spain",
    "sri lanka", "sudan", "suriname", "svalbard and jan mayen", "sweden", "switzerland", "syria",
    "taiwan", "tajikistan", "tanzania", "thailand", "timor-leste", "togo", "tokelau", "tonga",
    "trinidad and tobago", "tunisia", "turkey", "turkmenistan", "turks and caicos islands", "tuvalu",
    "uganda", "ukraine", "united arab emirates", "uae", "united kingdom", "uk", "united states",
    "united states of america", "usa", "uruguay", "uzbekistan", "vanuatu", "venezuela",
    "vietnam", "viet nam", "virgin islands", "wallis and futuna", "western sahara", "yemen",
    "zambia", "zealand", "zimbabwe"
}

_AMBIGUOUS_2LETTER_BLOCKLIST = {"it", "us", "in"}

def is_valid_country(country_str: str, original_str: Optional[str] = None, full_query: Optional[str] = None) -> bool:
    """
    Validate that country matches a known country name or ISO-3166-1 alpha-2 code.
    Blocks ambiguous lowercase 2-letter prepositions/pronouns (like "it", "us", "in")
    unless they are fully uppercase AND preceded by standard country prepositions in the full query.
    """
    if not country_str:
        return False
    c_clean = country_str.strip().lower()
    if not c_clean:
        return False

    # 1. Full country name check
    if c_clean in _COUNTRY_NAMES:
        return True

    # 2. ISO 2-letter code check
    if len(c_clean) == 2:
        c_upper = c_clean.upper()
        if c_upper in _ISO_COUNTRY_CODES:
            if c_clean in _AMBIGUOUS_2LETTER_BLOCKLIST:
                # Require original matched text to be fully uppercase
                if not original_str or original_str != c_upper:
                    return False
                # Require preceding preposition in full query
                if not full_query:
                    return False
                pattern = rf"\b(?:from|origin|of)\s+{re.escape(original_str)}\b"
                if not re.search(pattern, full_query):
                    return False
            return True

    return False


def looks_like_unit_price(query: str) -> bool:
    """
    Check if a query contains keywords or patterns indicating a unit cost/price
    rather than a total CIF value.
    """
    if not query:
        return False
    q_lower = query.lower()
    if any(phrase in q_lower for phrase in ["each", "per ", "unit price", "unit cost", "/unit", "/pcs"]):
        return True
    if re.search(r'\b1\s*(?:unit|pcs|pc|piece|head)\b', q_lower) and any(phrase in q_lower for phrase in ["cost", "price", "is", "value"]):
        return True
    return False


def is_entity_changed(entity_a: Optional[str], entity_b: Optional[str]) -> bool:
    """
    Compare two commodity entities to determine if they represent a different product.
    Known limitation: short/generic entities (e.g. "car" vs "car charger") 
    will falsely match as the same product and skip clearing.
    """
    if not entity_a or not entity_b:
        return False
    ea_lower = entity_a.lower().strip()
    eb_lower = entity_b.lower().strip()
    return ea_lower != eb_lower and ea_lower not in eb_lower and eb_lower not in ea_lower


