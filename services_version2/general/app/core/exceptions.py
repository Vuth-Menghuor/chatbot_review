"""
Compatibility re-exports for domain exceptions.

All domain exceptions are defined in ``app.exceptions.exceptions``.
This module exists so callers can import from ``app.core`` instead of
reaching directly into the exceptions package.
"""

from ..exceptions.exceptions import (
    DatabaseError,
    ForbiddenError,
    GDCEException,
    NotFoundError,
    RateLimitExceeded,
    ServiceUnavailable,
    UnauthorizedError,
    ValidationError,
)

__all__ = [
    "DatabaseError",
    "ForbiddenError",
    "GDCEException",
    "NotFoundError",
    "RateLimitExceeded",
    "ServiceUnavailable",
    "UnauthorizedError",
    "ValidationError",
]