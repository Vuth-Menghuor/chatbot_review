# Domain exceptions for general retrieval service
# Pure domain logic - NO framework imports


class GDCEException(Exception):
    """Base exception for GDCE general retrieval service."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(GDCEException):
    """Raised when input validation fails."""
    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(message, "VALIDATION_ERROR", 400)


class RateLimitExceeded(GDCEException):
    """Raised when rate limit is exceeded."""
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message, "RATE_LIMIT_EXCEEDED", 429)


class UnauthorizedError(GDCEException):
    """Raised when authorization fails."""
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, "UNAUTHORIZED", 401)


class ForbiddenError(GDCEException):
    """Raised when access is forbidden."""
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, "FORBIDDEN", 403)


class NotFoundError(GDCEException):
    """Raised when resource is not found."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, "NOT_FOUND", 404)


class ServiceUnavailable(GDCEException):
    """Raised when a dependent service is unavailable."""
    def __init__(self, service_name: str):
        message = f"{service_name} service is unavailable. Try again later."
        super().__init__(message, "SERVICE_UNAVAILABLE", 503)


class DatabaseError(GDCEException):
    """Raised when database operation fails."""
    def __init__(self, message: str = "Database error occurred"):
        super().__init__(message, "DATABASE_ERROR", 500)
