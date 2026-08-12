"""
API Module — General Retrieval Service.

Contains the FastAPI router, Pydantic request/response schemas, endpoint
handlers, and HTTP exception mapping for general / FAQ / definition /
policy queries against the ``gdce_docs`` collection.

Exports
-------
router : APIRouter
    The mounted FastAPI router with the ``/retrieval/retrieve`` endpoint.
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
