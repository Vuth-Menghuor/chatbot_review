"""External AI prompt files for the calculator service.

Prompts are stored as plain .txt files under this directory.
Python modules load and format them at runtime.
"""

from .intent_prompts import get_intent_extraction_prompt

__all__ = [
    "get_intent_extraction_prompt",
]
