"""
API module - Retrieval service
Contains FastAPI routes and request/response schemas
"""

from .endpoints import router
from .schemas import (
    QueryRequest,
    QueryResponse,
    DocumentResult,
    HealthCheckResponse,
)

__all__ = [
    "router",
    "QueryRequest",
    "QueryResponse",
    "DocumentResult",
    "HealthCheckResponse",
]