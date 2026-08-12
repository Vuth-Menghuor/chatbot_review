"""
Language Helpers — General Service.

Provides lightweight language detection (Khmer vs. English) and
language-aware text normalisation. When Khmer text is detected,
domain-relevant English hints are appended to support cross-lingual
semantic search (the embedding model is English-pretrained).
"""

from __future__ import annotations

from typing import Tuple
import re

# Khmer Unicode block (U+1780–U+17FF).
KHMER_RANGE = re.compile(r"[\u1780-\u17FF]")

# Map common Khmer customs/trade terms to English hints for query expansion.
KHMER_TERM_MAP = {
    "ពន្ធ": "tax duty",
    "គយ": "customs",
    "នាំចូល": "import",
    "នាំចេញ": "export",
    "លេខកូដ": "code",
    "លេខ hs": "hs code",
}


def detect_language(text: str) -> str:
    """Return ``"km"`` if Khmer characters are present, otherwise ``"en"``."""
    if KHMER_RANGE.search(text or ""):
        return "km"
    return "en"


def normalize_by_language(text: str) -> Tuple[str, str]:
    """
    Lowercase, collapse whitespace, and detect language.

    Returns ``(normalized_text, language_code)``.
    """
    language = detect_language(text)
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized, language


def expand_by_language(normalized_text: str, language: str) -> str:
    """
    Append English hints when Khmer customs terms are detected.

    This helps the embedding model (which is English-pretrained) produce
    better vectors for Khmer queries by injecting domain-relevant English
    tokens into the search text.
    """
    expanded = normalized_text
    if language == "km":
        for km_term, en_hint in KHMER_TERM_MAP.items():
            if km_term in normalized_text:
                expanded += f" {en_hint}"
    return expanded.strip()
