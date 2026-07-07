"""Filter parsing: convert query-string filter syntax to structured objects."""

from __future__ import annotations

from app.schemas.query import FilterItem, SortItem
import re

# Supported filter operators
VALID_OPERATORS = {"eq", "ne", "gt", "ge", "lt", "le", "in", "like"}


def parse_filters(raw_filters: list[str] | None) -> list[FilterItem]:
    """
    Parse repeatable filter strings like 'FIELD:op:value' into FilterItem list.

    Examples:
        >>> parse_filters(["PARTNER_COUNTRY:eq:US", "FLOW:eq:IMPORT"])
        [FilterItem(field='PARTNER_COUNTRY', operator='eq', value='US'),
         FilterItem(field='FLOW', operator='eq', value='IMPORT')]
    """
    if not raw_filters:
        return []

    items: list[FilterItem] = []
    for raw in raw_filters:
        parts = raw.split(":", 2)
        if len(parts) != 3:
            raise ValueError(
                f"Invalid filter format '{raw}'. Expected FIELD:operator:value"
            )
        field, operator, value = parts
        field = field.strip().upper()
        operator = operator.strip().lower()
        value = value.strip()

        if operator not in VALID_OPERATORS:
            raise ValueError(
                f"Unsupported filter operator '{operator}'. "
                f"Valid operators: {', '.join(sorted(VALID_OPERATORS))}"
            )

        items.append(FilterItem(field=field, operator=operator, value=value))

    return items


def parse_sort(raw_sort: str | None) -> list[SortItem]:
    """
    Parse a sort string like 'FIELD:desc' into a SortItem list.

    Examples:
        >>> parse_sort("FLOW:desc")
        [SortItem(field='FLOW', direction='desc')]
    """
    if not raw_sort:
        return []

    items: list[SortItem] = []
    for part in raw_sort.split(","):
        segments = part.strip().split(":", 1)
        field = segments[0].strip().upper()
        direction = segments[1].strip().lower() if len(segments) > 1 else "asc"

        if direction not in ("asc", "desc"):
            raise ValueError(
                f"Invalid sort direction '{direction}'. Must be 'asc' or 'desc'"
            )

        items.append(SortItem(field=field, direction=direction))

    return items

def split_period(period):
    period = period.strip()

    patterns = {
        "year": r"^\d{4}$",
        "month": r"^\d{4}-\d{2}$",
        "quarter": r"^\d{4}-q[1-4]$",
        "semester": r"^\d{4}-s[1-2]$",
    }

    for name, pattern in patterns.items():
        if re.fullmatch(pattern, period, flags=re.IGNORECASE):
            return period, period

    range_pattern = (
        r"^(?P<start>"
        r"\d{4}"
        r"(?:-\d{2}|-q[1-4]|-s[1-2])?"
        r")-(?P<end>"
        r"\d{4}"
        r"(?:-\d{2}|-q[1-4]|-s[1-2])?"
        r")$"
    )

    m = re.fullmatch(range_pattern, period, flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid period format: {period}")

    return m.group("start"), m.group("end")