"""
GDCE Calculator Service - Intent Extraction Prompts
====================================================
Prompt templates for the LLM intent extractor.

Loads plain-text prompt files and formats them with runtime variables.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Any


_PROMPTS_DIR = Path(__file__).parent


def _load_prompt(name: str, **kwargs: Any) -> str:
    """Load a prompt template from a .txt file and substitute variables."""
    path = _PROMPTS_DIR / f"{name}.txt"
    template = path.read_text(encoding="utf-8")
    return template.format(**kwargs)


def get_intent_extraction_prompt(user_query: str) -> str:
    """Return the full intent-extraction prompt for the given user query."""
    today = datetime.now().strftime("%Y-%m-%d")
    return _load_prompt(
        "intent_extraction",
        today=today,
        user_query=user_query,
    )


__all__ = ["get_intent_extraction_prompt"]
