"""Dynamic product-to-HS-code resolution.

Fetches HS chapter and heading mappings live from the DAL metadata endpoint,
caching results in-process.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional

try:
    import httpx as _httpx
except ImportError:
    _httpx = None  # type: ignore

logger = logging.getLogger(__name__)

_PRODUCT_KEYWORD_MAP: Dict[str, str] | None = None

# Stop-words that are too generic to use as product keywords
_LABEL_STOP_WORDS = frozenset({
    "other", "live", "fresh", "chilled", "frozen", "dried", "salted", "smoked",
    "parts", "preparations", "products", "articles", "goods", "materials",
    "thereof", "such", "including", "excluding", "similar", "related",
    "miscellaneous", "various", "special", "general", "certain", "edible",
    "from", "with", "into", "onto", "upon", "within", "without", "between",
    "through", "during", "before", "after", "above", "below", "under",
    "over", "near", "about", "along", "across", "against", "among",
    "and", "but", "nor", "for", "yet", "both", "either", "neither",
    "not", "only", "whether", "that", "this", "these", "those",
    "the", "its", "their", "which", "when", "where", "who", "whom",
    "designed", "used", "fitted", "made", "derived", "obtained", "produced",
    "rendered", "processed", "refined", "treated", "mixed", "combined",
    "type", "form", "kind", "sort", "item", "unit", "piece", "set",
    "base", "pure", "raw", "new", "old", "used", "waste", "scrap",
    "all", "any", "every", "each", "some", "few", "many", "several",
    "import", "imports", "export", "exports", "trade", "volume", "value",
    "values", "summary", "overall", "show", "give", "find", "get", "list",
    "air", "sea", "land", "rail", "road", "port", "airport", "via", "by",
    "freight", "cargo", "transport",
})


def _build_terms_from_label(label: str) -> list[str]:
    """Split an HS label into indexable keyword terms."""
    label = label.strip().rstrip(".\n\r").lower()
    first_segment = re.split(r"[,;]", label)[0].strip()
    first_segment = re.split(r"\bfor\b|\bof\b|\bnot\b|\bwhether\b|\bexcluding\b", first_segment)[0].strip()

    terms: list[str] = []
    cleaned = first_segment.rstrip(".").strip()
    if 2 <= len(cleaned) <= 40 and cleaned not in _LABEL_STOP_WORDS:
        terms.append(cleaned)

    for part in re.split(r"\band\b", first_segment):
        word_phrase = part.strip().rstrip(".").strip()
        if 2 <= len(word_phrase) <= 40 and word_phrase not in _LABEL_STOP_WORDS:
            if word_phrase not in terms:
                terms.append(word_phrase)
        for word in word_phrase.split():
            word = word.strip().rstrip(".")
            if len(word) >= 3 and word not in _LABEL_STOP_WORDS and word not in terms:
                terms.append(word)

    return list(dict.fromkeys(terms))


def _get_product_keyword_map() -> dict[str, str]:
    """Return a mapping of lowercase product keyword → HS heading/chapter code."""
    global _PRODUCT_KEYWORD_MAP
    if _PRODUCT_KEYWORD_MAP is not None:
        return _PRODUCT_KEYWORD_MAP

    mapping: dict[str, str] = {}

    dal_base = os.getenv("DAL_BASE_URL", "http://172.25.3.243:8989").rstrip("/")
    dal_api_key = os.getenv("DAL_API_KEY", "")
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
        from dal.exceptions import DALError
        status_code = getattr(getattr(exc, "response", None), "status_code", 502)
        logger.error(f"[_get_product_keyword_map] Could not fetch DAL metadata ({metadata_url}): {exc}")
        raise DALError(f"Could not fetch DAL metadata from {metadata_url}: {exc}", status_code=status_code) from exc

    meta = resp.json()

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

    for term, code in hs_heading_entries:
        if term not in mapping:
            mapping[term] = code

    for term, code in hs_chapter_entries:
        if term not in mapping:
            mapping[term] = code

    logger.info(f"[_get_product_keyword_map] Loaded {len(mapping)} product terms from DAL metadata ({metadata_url})")
    _PRODUCT_KEYWORD_MAP = mapping
    return _PRODUCT_KEYWORD_MAP


def resolve_product_to_hs(product_name: str) -> Optional[str]:
    """Resolve a raw product name description to a numeric HS chapter or heading."""
    name_lower = product_name.lower().strip()
    
    # 1. Direct semantic mapping for generic industry terms
    semantic_map = {
        "garment": "61",
        "clothing": "61",
        "apparel": "61",
        "footwear": "64",
        "shoe": "64",
        "rice": "1006",
        "electronics": "85",
        "electronic": "85"
    }
    
    for term, code in semantic_map.items():
        if term in name_lower:
            return code

    # 2. Explicitly tagged HS codes (e.g. 'HS 8471', 'HS code 2709')
    match = re.search(r"\b(?:heading|code|hs|hs\s+code)\s+(\d{4,8})\b", product_name, re.IGNORECASE)
    if match:
        return match.group(1)

    # 3. Match longest phrase keys first from the live mapping
    try:
        product_map = _get_product_keyword_map()
        for key in sorted(product_map.keys(), key=len, reverse=True):
            pattern = rf"\b{re.escape(key)}\b"
            if re.search(pattern, name_lower):
                return product_map[key]
    except Exception as exc:
        logger.warning(f"[resolve_product_to_hs] Live mapping resolution failed: {exc}")

    return None