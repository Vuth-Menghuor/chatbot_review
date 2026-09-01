"""
Central API Router - Orchestrator service

This module is the single import point for the FastAPI application.
``main.py`` should import from here instead of directly from endpoints:

    from .api.routes import router
    app.include_router(router)

All versioned and utility sub-routers are assembled here so that
``main.py`` stays free of router-management boilerplate.

Layout:
    POST /query            — process a user query
    POST /chat             — alias for /query
    POST /query/explain    — debug: explain routing for a query
    GET  /info             — service capabilities and endpoint list
    GET  /                 — root / service info
    GET  /health           — liveness probe  (from health_routes)
    GET  /ready            — readiness probe (from health_routes)
    GET  /status           — detailed dependency status (from health_routes)

Migration note:
    /health and /status were previously defined in endpoints.py.
    They are now owned by health_routes.py (health_router).
    Once this central router is active in main.py, remove the
    duplicate /health and /status definitions from endpoints.py.
"""

from fastapi import APIRouter

from .endpoints import router as v1_router
from .health_routes import health_router

# Top-level router that main.py includes
router = APIRouter()

# v1 business-logic endpoints — keep existing paths unchanged
# (POST /query, POST /chat, POST /query/explain, GET /info, GET /)
#
# NOTE: /health and /status in endpoints.py will be shadowed by the
# health_router below once main.py switches to this central router.
# Remove those duplicates from endpoints.py after the switch.
router.include_router(v1_router)

# Health / observability endpoints
# Provides: GET /health, GET /ready, GET /status
router.include_router(health_router)
