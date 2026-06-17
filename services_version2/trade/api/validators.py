"""Input validators for trade_query API."""

from __future__ import annotations

import re

from .exceptions import InvalidInputError

MIN_YEAR = 2000
MAX_YEAR = 2100

from ..core.countries import VALID_COUNTRY_CODES


def validate_question(question: str | None) -> str:
    if not question or not isinstance(question, str):
        raise InvalidInputError("Question must be a non-empty string")
    question = question.strip()
    if len(question) < 5:
        raise InvalidInputError("Question must be at least 5 characters")
    return question


def validate_year_range(year: int | None) -> None:
    if year is None:
        return
    if not isinstance(year, int) or year < MIN_YEAR or year > MAX_YEAR:
        raise InvalidInputError(f"Year must be between {MIN_YEAR} and {MAX_YEAR}")


def validate_country_code(code: str | None) -> None:
    if code is None:
        return
    if code.upper() not in VALID_COUNTRY_CODES:
        raise InvalidInputError(f"Unsupported country code: {code}")


def validate_hs_code(hs_code: str | None) -> None:
    if hs_code is None:
        return
    if not re.match(r"^\d{4,8}$", hs_code):
        raise InvalidInputError("HS code must be 4-8 digits")
