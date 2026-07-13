"""Numeric utility functions for GDCE Trade Query Service visualization."""

from typing import Any


def to_float(v: Any) -> float:
    """Safe conversion of a value to float, returning 0.0 on failure."""
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0
