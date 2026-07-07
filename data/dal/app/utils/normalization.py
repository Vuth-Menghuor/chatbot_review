"""Input normalization utilities for deterministic processing."""

from __future__ import annotations


def normalize_list(raw: str | None) -> list[str]:
    """
    Parse a comma-separated string into a upper-cased, deduplicated list.

    Examples:
        >>> normalize_list("FREQ,partner_country,FLOW")
        ['FREQ', 'PARTNER_COUNTRY', 'FLOW']
    """
    if not raw:
        return []
    items = [item.strip().upper() for item in raw.split(",") if item.strip()]
    return list(set(items))


def normalize_string(value: str | None) -> str | None:
    """Strip and upper-case a single value."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped.upper() if stripped else None
