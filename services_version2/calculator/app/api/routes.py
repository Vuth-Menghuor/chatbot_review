"""
GDCE Calculator Service - API Routes
====================================
Registers the versioned router from api.endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from .v1.calculator_routes import router as endpoints_router
from ..converter.routes import router as converter_router

router = APIRouter()

# Mount all endpoints under this router
router.include_router(endpoints_router)
router.include_router(converter_router)
