# HTTP exception mapping layer for general service
# Re-exports domain exceptions and provides HTTP mapping functions
from fastapi import HTTPException

try:
    from ..core.exceptions import (
        GDCEException,
        ValidationError,
        RateLimitExceeded,
        UnauthorizedError,
        ForbiddenError,
        NotFoundError,
        ServiceUnavailable,
        DatabaseError,
    )
except ImportError:
    from core.exceptions import (
        GDCEException,
        ValidationError,
        RateLimitExceeded,
        UnauthorizedError,
        ForbiddenError,
        NotFoundError,
        ServiceUnavailable,
        DatabaseError,
    )

__all__ = [
    "GDCEException",
    "ValidationError",
    "RateLimitExceeded",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "ServiceUnavailable",
    "DatabaseError",
    "to_http_exception",
]


def to_http_exception(exc: GDCEException) -> HTTPException:
    """Map domain exception to FastAPI HTTPException."""
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error_code": exc.code,
            "message": exc.message
        }
    )
