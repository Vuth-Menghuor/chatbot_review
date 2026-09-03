"""
Dynamic prompt loading for the Retrieval Service.

Prompts are stored as plain-text ``.txt`` files in this directory and
loaded at call time via ``get_prompt()``. The ``render_prompt()`` helper
applies Python ``str.format(**kwargs)`` substitution so callers can inject
query text, candidate lists, and constraint metadata without manual string
concatenation.

Usage
-----
    from prompts import render_prompt

    prompt = render_prompt("gemini_ranked_hs.txt", query="BMW M8", candidates="...", limit=5)
"""

from .loader import get_prompt, render_prompt

__all__ = ["get_prompt", "render_prompt"]