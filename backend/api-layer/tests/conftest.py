from __future__ import annotations

from pathlib import Path
import sys


# Make `app.*` imports work when pytest is run from the api-layer directory or repo root.
API_LAYER_ROOT = Path(__file__).resolve().parents[1]
if str(API_LAYER_ROOT) not in sys.path:
    sys.path.insert(0, str(API_LAYER_ROOT))
