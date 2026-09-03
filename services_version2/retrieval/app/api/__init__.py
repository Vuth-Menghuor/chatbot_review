"""
API Module — Retrieval Service.

Contains the FastAPI router, Pydantic request/response schemas, and endpoint
handlers for the HS-code classification service.

Exports
-------
router : APIRouter
    The mounted FastAPI router with all retrieval endpoints.
QueryRequest / QueryResponse / DocumentResult / HealthCheckResponse
    Pydantic models for request validation and response serialisation.
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