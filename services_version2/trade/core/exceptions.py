"""Service-level exceptions for trade_query."""


class ValidationError(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


class UnknownIntentError(Exception):
    def __init__(self, intent: str):
        super().__init__(f"Unknown intent: {intent}")
        self.intent = intent


class NoResultsError(Exception):
    def __init__(self, message: str = "No results found", query_params: dict | None = None, dal_source_url: str | None = None):
        super().__init__(message)
        self.message = message
        self.query_params = query_params
        self.dal_source_url = dal_source_url


class NormalisationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

