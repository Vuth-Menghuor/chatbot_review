"""
HTTP Exception Mapping — General Retrieval Service.

Re-exports domain exceptions from ``app.exceptions`` and provides a
``to_http_exception()`` mapper that converts domain-layer exceptions
into FastAPI ``HTTPException`` instances suitable for API responses.

This keeps the HTTP framework concern out of the domain layer while
providing a single place to map error codes and status codes.
"""

from fastapi import HTTPException

# Re-export domain exceptions so callers only need to import from here.
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
    """
    Map a domain exception to a FastAPI ``HTTPException``.

    The domain exception carries its own HTTP status code and error code,
    so no per-type mapping is needed — the exception is self-describing.

    Parameters
    ----------
    exc : GDCEException
        Any domain exception with ``status_code``, ``code``, and ``message``.

    Returns
    -------
    HTTPException
        A FastAPI exception ready to be raised in an endpoint handler.
    """
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "error_code": exc.code,
            "message": exc.message,
        },
    )
