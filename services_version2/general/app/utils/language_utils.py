"""Language helpers for general service query preprocessing."""

from __future__ import annotations

from typing import Tuple
import re


KHMER_RANGE = re.compile(r"[\u1780-\u17FF]")

KHMER_TERM_MAP = {
    "ពន្ធ": "tax duty",
    "គយ": "customs",
    "នាំចូល": "import",
    "នាំចេញ": "export",
    "លេខកូដ": "code",
    "លេខ hs": "hs code",
}


def detect_language(text: str) -> str:
    if KHMER_RANGE.search(text or ""):
        return "km"
    return "en"


def normalize_by_language(text: str) -> Tuple[str, str]:
    language = detect_language(text)
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized, language


def expand_by_language(normalized_text: str, language: str) -> str:
    expanded = normalized_text
    if language == "km":
        for km_term, en_hint in KHMER_TERM_MAP.items():
            if km_term in normalized_text:
                expanded += f" {en_hint}"
    return expanded.strip()
