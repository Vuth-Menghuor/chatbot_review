"""
Prompt loader — reads and renders file-backed prompt templates.

All prompt templates live as ``.txt`` files in the same directory as this
module. They are loaded on each call (no caching) so edits take effect
without a restart.

``render_prompt`` applies Python's ``str.format(**kwargs)`` to inject
dynamic content (query text, context blocks, retry sections, etc.).

.. warning::
    ``str.format`` will raise ``KeyError`` if a prompt template references
    a variable that was not passed. Ensure the caller provides all required
    keyword arguments.
"""

from __future__ import annotations

from pathlib import Path

# Absolute path to this directory — prompt files are resolved relative to it.
PROMPTS_DIR = Path(__file__).resolve().parent


def get_prompt(name: str) -> str:
    """
    Read a prompt template from disk.

    Parameters
    ----------
    name : str
        Filename relative to the prompts directory
        (e.g. ``"gemini_user.txt"``).

    Returns
    -------
    str
        The raw template text, with leading/trailing whitespace stripped.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, **kwargs) -> str:
    """
    Load a prompt template and substitute ``{key}`` placeholders.

    Parameters
    ----------
    name : str
        Prompt filename (see ``get_prompt``).
    **kwargs
        Keyword arguments passed to ``str.format``.

    Returns
    -------
    str
        The rendered prompt string with all placeholders replaced.
    """
    return get_prompt(name).format(**kwargs)