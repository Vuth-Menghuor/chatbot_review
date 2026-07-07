"""Period format parsing and validation against metadata rules."""

from __future__ import annotations

import re

def split_period(period: str) -> tuple[str, str]:
    ''' 
    Period should follow the pattern
    - yyyy-yyyy for year to year
    - yyyy-mm-yyyy-mm for month to month
    - yyyy-qn-yyyy-qn for quarter to quarter
    - yyyy-sn-yyyy-sn for semester to semester
    - if only one period is provided (yyyy, yyyy-mm, yyyy-qn, yyyy-sn), it will be treated as start_period and end_period
    '''
    
    period = period.strip()
    if " - " in period:
        start, end = period.split(" - ", 1)
        period = f"{start.strip()}-{end.strip()}"

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