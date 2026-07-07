"""Unified error codes and exception classes."""

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import HTTPException


class ErrorCode(str, Enum):
    """Canonical error codes returned in API error envelopes."""

    MISSING_API_KEY = "MISSING_API_KEY"
    INVALID_API_KEY = "INVALID_API_KEY"
    INACTIVE_API_KEY = "INACTIVE_API_KEY"
    MISSING_SCOPE = "MISSING_SCOPE"
    FORBIDDEN_DATASET = "FORBIDDEN_DATASET"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
    INVALID_DIMENSION = "INVALID_DIMENSION"
    INVALID_MEASURE = "INVALID_MEASURE"
    INVALID_FILTER = "INVALID_FILTER"
    INVALID_SORT = "INVALID_SORT"
    INVALID_PERIOD = "INVALID_PERIOD"
    INVALID_FREQUENCY = "INVALID_FREQUENCY"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_VALUE = "INVALID_VALUE"


# Map error codes to HTTP status codes
_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.MISSING_API_KEY: 401,
    ErrorCode.INVALID_API_KEY: 401,
    ErrorCode.INACTIVE_API_KEY: 403,
    ErrorCode.MISSING_SCOPE: 403,
    ErrorCode.FORBIDDEN_DATASET: 403,
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    ErrorCode.DATASET_NOT_FOUND: 404,
    ErrorCode.VERSION_NOT_FOUND: 404,
    ErrorCode.INVALID_DIMENSION: 400,
    ErrorCode.INVALID_MEASURE: 400,
    ErrorCode.INVALID_FILTER: 400,
    ErrorCode.INVALID_SORT: 400,
    ErrorCode.INVALID_PERIOD: 400,
    ErrorCode.INVALID_FREQUENCY: 400,
    ErrorCode.INVALID_VALUE: 400,
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.INTERNAL_ERROR: 500,
}


class DALError(HTTPException):
    """Application-level error with a structured error code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        headers: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = code
        self.error_message = message
        status_code = _STATUS_MAP.get(code, 500)
        super().__init__(status_code=status_code, detail=message, headers=headers)
