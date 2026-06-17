"""DAL-specific exceptions."""


class DALError(Exception):
    """Raised when a DAL request fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
