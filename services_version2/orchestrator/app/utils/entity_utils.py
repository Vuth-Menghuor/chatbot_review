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

    # Step 4: Strip trailing key=value parameters (cif is $..., dv=..., cif=..., dq ...)
    # e.g. "car cif is $10500 from china acfta rate dv=0" → "car"
    text = re.sub(r"\s+(?:hs|cif|fob|dv|dq|acfta|atiga|rcep|from|rate|origin)[\s=:][^,]+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"[,;\s]*cif\s*(?:is\s*)?\$?\d[\d,.]*(?:\s*(?:usd|khr|dollars|eur|cif))?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"[,;\s]*(?:importing\s+)?from\s+[a-z]+(?:\s+[a-z]+)?", "", text, flags=re.IGNORECASE).strip()

    # Step 5: Strip any residual trailing punctuation
    text = re.sub(r"[?!.,;:]+$", "", text).strip()

    # Step 6: Remove obvious stopwords that survived stripping
    STOPWORDS = {"a", "an", "the", "its", "it", "that", "this", "these", "those", "some", "importing", "exporting", "code", "use", "using", "try", "correct", "right"}
    words = text.split()
    words = [w for w in words if w not in STOPWORDS]
    text = " ".join(words).strip()

    # Return None when nothing meaningful is left (empty or single char)
    if not text or len(text) <= 1:
        return None

    return text


def clean_hs_query_for_retrieval(query: str) -> str:
    """
    Strips common prefix phrases related to HS code requests, leaving only
    the commercial or product description. Preserves casing and technical details.
    """
    if not query:
        return ""

    text = query.strip()
    changed = True
    while changed:
        changed = False
        for pattern in _HS_PREFIX_PATTERNS:
            new_text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                changed = True
                break

    text = re.sub(r"^[?.,\s]+", "", text)
    text = re.sub(r"[?.,\s]+$", "", text)

    return text if text else query