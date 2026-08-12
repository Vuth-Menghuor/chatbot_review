"""
Dynamic prompt loading for the General Retrieval Service.

Prompts are stored as plain-text ``.txt`` files in this directory and
loaded at call time via ``get_prompt()``. The ``render_prompt()`` helper
applies Python ``str.format(**kwargs)`` substitution.

Usage
-----
    from prompts import render_prompt

    prompt = render_prompt("gemini_user.txt", query="...", context_section="...")
"""

from .loader import get_prompt, render_prompt

__all__ = ["get_prompt", "render_prompt"]