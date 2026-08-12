"""
Domain Exceptions — General Retrieval Service.

Pure domain-layer exception hierarchy. These exceptions carry their own
HTTP status codes and error codes so the API mapping layer
(``app.api.exceptions.to_http_exception``) can translate them without
needing per-type logic.

All exceptions extend ``GDCEException``, which holds:
- ``message`` — human-readable description.
- ``code`` — machine-readable error code string.
- ``status_code`` — HTTP status code for the API response.
"""


class GDCEException(Exception):
    """
    Base exception for the GDCE general retrieval service.

    Parameters
    ----------
    message : str
        Human-readable error description.
    code : str
        Machine-readable error code (e.g. ``"INTERNAL_ERROR"``).
    status_code : int
        HTTP status code to return to the client.
    """

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(GDCEException):
    """Raised when input validation fails (HTTP 400)."""

    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(message, "VALIDATION_ERROR", 400)


class RateLimitExceeded(GDCEException):
    """Raised when the request rate limit is exceeded (HTTP 429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message, "RATE_LIMIT_EXCEEDED", 429)


class UnauthorizedError(GDCEException):
    """Raised when authentication is missing or invalid (HTTP 401)."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, "UNAUTHORIZED", 401)


class ForbiddenError(GDCEException):
    """Raised when the authenticated user lacks permission (HTTP 403)."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, "FORBIDDEN", 403)


class NotFoundError(GDCEException):
    """Raised when a requested resource does not exist (HTTP 404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, "NOT_FOUND", 404)


class ServiceUnavailable(GDCEException):
    """Raised when a dependent service is unavailable (HTTP 503)."""

    def __init__(self, service_name: str):
        message = f"{service_name} service is unavailable. Try again later."
        super().__init__(message, "SERVICE_UNAVAILABLE", 503)


class DatabaseError(GDCEException):
    """Raised when a database operation fails (HTTP 500)."""


class DatabaseError(GDCEException):
    """Raised when database operation fails."""
    def __init__(self, message: str = "Database error occurred"):
        super().__init__(message, "DATABASE_ERROR", 500)
