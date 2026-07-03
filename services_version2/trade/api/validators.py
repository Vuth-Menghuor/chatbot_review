"""Input validators for trade_query API."""

from __future__ import annotations

import re

from api.exceptions import InvalidInputError

from config import get_settings

from core.countries import VALID_COUNTRY_CODES


def validate_question(question: str | None) -> str:
    settings = get_settings()
    if not question or not isinstance(question, str):
        raise InvalidInputError("Question must be a non-empty string")
    question = question.strip()
    if len(question) < settings.min_question_length:
        raise InvalidInputError(f"Question must be at least {settings.min_question_length} characters")
    return question


def validate_year_range(year: int | None) -> None:
    if year is None:
        return
    settings = get_settings()
    if not isinstance(year, int) or year < settings.min_validation_year or year > settings.max_validation_year:
        raise InvalidInputError(f"Year must be between {settings.min_validation_year} and {settings.max_validation_year}")


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
