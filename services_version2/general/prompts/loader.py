"""
Prompt loader for file-backed dynamic prompts.
"""

from __future__ import annotations

from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent


def get_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, **kwargs) -> str:
    """Load and format a prompt template."""
    return get_prompt(name).format(**kwargs)