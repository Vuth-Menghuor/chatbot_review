"""
GDCE Calculator Service - API Package
======================================
FastAPI routers and HTTP-layer models.

Exports:
    router - Main API router with all calculator endpoints
    schemas - Request/response models

Usage:
    from calculator.app.api import router
    app.include_router(router)
"""

from .routes import router

__all__ = ["router"]
