"""
Prompt loader for file-backed retrieval prompts.
"""

from __future__ import annotations

from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent


def get_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, **kwargs) -> str:
    return get_prompt(name).format(**kwargs)