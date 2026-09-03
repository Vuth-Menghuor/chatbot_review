"""
Shared pytest fixtures and ``sys.path`` setup for the Retrieval Service tests.

The service uses a mixed absolute / relative import style
(``from prompts import render_prompt``, ``from ..rag.service import ...``),
so the repository root (the ``retrieval/`` directory containing both
``app/`` and ``prompts/``) **must** be on ``sys.path`` for imports to
resolve the same way they do at runtime (see ``app/app.py``'s
``try/except ImportError`` block).

This conftest ensures that ``pytest`` works regardless of the working
directory or how it's invoked.
"""

import sys
from pathlib import Path

# The repo root is one level up from this ``tests/`` directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))