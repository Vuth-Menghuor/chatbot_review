"""HTTP-specific exception wrappers for trade_query."""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.exceptions import (
    NoResultsError,
    NormalisationError,
    UnknownIntentError,
    ValidationError,
)
from app.dal.exceptions import DALError


class InvalidInputError(HTTPException):
    def __init__(self, message: str = "Invalid input"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


class NotFoundError(HTTPException):
    def __init__(self, message: str = "No results found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=message)


class DALServiceError(HTTPException):
    def __init__(self, message: str = "DAL service error"):
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=message)


class QueryTimeoutError(HTTPException):
    def __init__(self, message: str = "Query timeout"):
        super().__init__(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=message)


def map_core_exception_to_http(exc: Exception) -> HTTPException:
    """Map core/domain exceptions to HTTP exceptions."""
    if isinstance(exc, ValidationError):
        return InvalidInputError(str(exc))
    if isinstance(exc, UnknownIntentError):
        return InvalidInputError(str(exc))
    if isinstance(exc, NoResultsError):
        return NotFoundError(str(exc))
    if isinstance(exc, DALError):
        status_code = exc.status_code or 502
        if status_code == 504:
            return QueryTimeoutError(str(exc))
        return DALServiceError(str(exc))
    if isinstance(exc, NormalisationError):
        return DALServiceError(str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An internal error occurred.",
    )
