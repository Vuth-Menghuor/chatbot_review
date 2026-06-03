"""
Core module - Retrieval service
Contains query processing, ranking, and retrieval logic
"""

from .query import QueryProcessor
from .retrieval import RetrievalOrchestrator
from .service import RetrievalService
from .answer_generator import AnswerGenerator
from .exceptions import (
    GDCEException,
    ValidationError,
    RateLimitExceeded,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailable,
    InvalidCalculation,
    DatabaseError,
)

__all__ = [
    "QueryProcessor",
    "RetrievalOrchestrator",
    "RetrievalService",
    "AnswerGenerator",
    # Exceptions
    "GDCEException",
    "ValidationError",
    "RateLimitExceeded",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "ServiceUnavailable",
    "InvalidCalculation",
    "DatabaseError",
]
