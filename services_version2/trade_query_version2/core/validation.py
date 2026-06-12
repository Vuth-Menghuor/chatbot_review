"""Natural-language parameter extraction for trade_query.

Product-to-HS-code resolution is fetched live from the DAL metadata endpoint
(/v1/metadata/dataset/{dataset}), covering all HS chapters and headings tracked
by the dataset.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

try:
    import httpx as _httpx
except ImportError:  # pragma: no cover
    _httpx = None  # type: ignore[assignment]

from .exceptions import ValidationError

logger = logging.getLogger(__name__)


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
    
    # Post-resolve HS code if LLM returned a product name
    hs_code = params.get("hs_code")
    if hs_code and not hs_code.isdigit():
        resolved_hs = _extract_hs_code(hs_code)
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

    # Try LLM parameter extraction
    try:
        from .llm_extractor import extract_parameters_llm
        llm_params = extract_parameters_llm(question)
        if llm_params is None:
            raise ValidationError("LLM parameter extraction returned no parameters", field="question")
        logger.info(f"[extract_parameters] LLM extracted successfully: {llm_params}")
        return post_resolve_parameters(llm_params, question)
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        logger.error(f"[extract_parameters] LLM parameter extraction errored: {e}")
        raise ValidationError(f"LLM parameter extraction failed: {str(e)}", field="question") from e


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

    if _httpx is None:
        raise ImportError("httpx not available")
    try:
        resp = _httpx.get(
            metadata_url,
            headers={"Accept": "application/json", "x-api-key": dal_api_key},
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception as exc:
        from ..dal.exceptions import DALError
        status_code = getattr(getattr(exc, "response", None), "status_code", 502)
        logger.error(
            f"[_get_product_keyword_map] Could not fetch DAL metadata ({metadata_url}): {exc}"
        )
        raise DALError(f"Could not fetch DAL metadata from {metadata_url}: {exc}", status_code=status_code) from exc

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
