"""Shared handler helpers."""

from __future__ import annotations

from typing import Any

from .strategies import IntentStrategy


def resolve_period_range(params: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """Derive period / start_period / end_period / frequency from params."""

    period = params.get("period")
    if isinstance(period, str) and period.strip():
        return period, params.get("start_period"), params.get("end_period"), params.get("frequency")

    start_period = params.get("start_period")
    end_period = params.get("end_period")
    if start_period or end_period:
        return None, start_period, end_period, params.get("frequency")

    year = params.get("year")
    quarter = params.get("quarter")
    month = params.get("month")

    if year is None:
        return None, None, None, params.get("frequency")

    year_text = str(year)
    if quarter:
        return f"{year_text}-{quarter}", None, None, params.get("frequency") or "Q"

    if month is not None:
        month_text = str(month).zfill(2)
        return f"{year_text}-{month_text}", None, None, params.get("frequency") or "M"

    return year_text, None, None, params.get("frequency") or "A"


def resolve_limit(params: dict[str, Any], strategy: IntentStrategy) -> int:
    """Return the effective limit: param override > strategy default > global default."""
    explicit = params.get("limit")
    if explicit is not None:
        try:
            return int(explicit)
        except (ValueError, TypeError):
            pass
    return strategy.default_limit
