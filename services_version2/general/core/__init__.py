"""
Core module - General Retrieval Service
Contains query processing, retrieval orchestration, and business logic
for general (non-HS) document retrieval.
"""

from .query import QueryProcessor
from .retrieval import RetrievalOrchestrator
from .service import GeneralRetrievalService
from .answer_generator import AnswerGenerator
from .exceptions import (
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
    "QueryProcessor",
    "RetrievalOrchestrator",
    "GeneralRetrievalService",
    "AnswerGenerator",
    # Exceptions
    "GDCEException",
    "ValidationError",
    "RateLimitExceeded",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "ServiceUnavailable",
    "DatabaseError",
]
