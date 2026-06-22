"""
GDCE Calculator Service - API Routes
====================================
Registers the versioned router from api.endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

from .endpoints import router as endpoints_router

router = APIRouter()

# Mount all endpoints under this router
router.include_router(endpoints_router)
