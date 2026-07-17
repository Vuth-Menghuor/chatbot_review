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

from string import punctuation
import re
from typing import Optional


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

    # Step 2: Strip leading intent-keyword prefixes iteratively.
    # Chained prefixes collapse on repeated passes.
    PREFIXES = [
        # HS-code signals
        r"^(?:what(?:'?s|\s+is)?(?:\s+the)?\s+)?hs\s*(?:code|codes|number|tariff)?\s*(?:of|for|on)?\s*",
        r"^(?:find|get|look\s+up|give\s+me|tell\s+me)(?:\s+the)?\s+hs\s*(?:code|codes|number)?\s*(?:of|for|on)?\s*",
        r"^classify(?:\s+the)?\s*(?:product)?\s*",
        # Trade-query signals
        r"^(?:what(?:'?s|\s+is)?(?:\s+the)?\s+)?trade\s+(?:data|statistics|volume|flow|flows)?\s*(?:of|for|on|about)?\s*",
        r"^(?:import|export)\s+(?:data|statistics|volume|flow)?\s*(?:of|for|on|from|to)?\s*",
        # Calculation signals
        r"^(?:calculate|compute|how\s+much\s+(?:is|are|does)?)\s+(?:the\s+)?(?:import\s+)?(?:duty|tax|tariff|vat|fee)?\s*(?:of|for|on)?\s*",
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
    ]

    changed = True
    while changed:
        changed = False
        for prefix_pattern in PREFIXES:
            new_text = re.sub(prefix_pattern, "", text, flags=re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                changed = True
                break  # restart loop so earlier patterns re-run

    # Step 3: Strip any residual trailing punctuation
    text = re.sub(r"[?!.,;:]+$", "", text).strip()

    # Step 4: Remove obvious stopwords that survived stripping
    STOPWORDS = {"a", "an", "the", "its", "it", "that", "this", "these", "those", "some"}
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

    prefixes = [
        r"^(?:what(?:'?s|\s+is)?(?:\s+the)?\s+)?hs\s*(?:code|codes|number|tariff)?\s*(?:of|for|on|about)?\s*",
        r"^(?:find|get|look\s+up|give\s+me|tell\s+me|show)(?:\s+the)?\s+hs\s*(?:code|codes|number|tariff)?\s*(?:of|for|on|about)?\s*",
        r"^classify(?:\s+the)?\s*(?:product)?\s*",
        r"^(?:please\s+)?(?:tell\s+me\s+)?how\s+to\s+classify\s*",
    ]

    text = query.strip()
    changed = True
    while changed:
        changed = False
        for pattern in prefixes:
            new_text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                changed = True
                break

    text = re.sub(r"^[?.,\s]+", "", text)
    text = re.sub(r"[?.,\s]+$", "", text)

    return text if text else query