"""
Compatibility exports for domain exceptions.
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