"""
GDCE Calculator Service - Application Factory
==============================================
Creates and configures the FastAPI application instance.
Import this module to get the fully-configured app for use with
uvicorn, gunicorn, or tests.

Version: 2.0  (microservice skeleton)
Last Updated: 2026-03-25
"""

from __future__ import annotations

import os
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables from the calculator service .env file
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Application factory.

    Returns a fully configured FastAPI instance with:
    - Security middleware (rate limiting, CORS)
    - API routers registered under /v1
    - Global exception handlers
    - Startup / shutdown lifecycle hooks

    Usage:
        from calculator_version2.app import create_app
        app = create_app()
    """
    from .config import get_settings
    from .api.routes import router as calculator_router

    settings = get_settings()

    app = FastAPI(
        title="GDCE Calculator Service",
        description="Import tax calculation service for Cambodia customs (GDCE)",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------
    _register_middleware(app, settings)

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    app.include_router(calculator_router)

    # ------------------------------------------------------------------
    # Dynamic Rules Engine — Admin Router
    # ------------------------------------------------------------------
    _init_rules_engine(app, settings)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info("Calculator Service starting up — version %s", settings.calculator_version)
        # Pre-warm database so the first request doesn't pay the cold-start cost
        try:
            from .api.deps import get_db
            db_gen = get_db()
            next(db_gen)
            logger.info("Database pre-warmed successfully")
        except Exception as e:
            logger.warning(f"Database pre-warm failed (will lazy-load on first request): {e}")

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("Calculator Service shutting down")

    # ------------------------------------------------------------------
    # Global exception handler (catch-all)
    # ------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Any, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "detail": str(exc)},
        )

    return app


def _register_middleware(app: FastAPI, settings: Any) -> None:
    """
    Attach CORS and rate-limiting middleware to the app.
    Self-contained — no external shared package dependency.
    """
    # ---- CORS ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Simple Rate Limiting ----
    request_counts: Dict[str, list] = defaultdict(list)
    max_rpm = settings.rate_limit_requests
    max_payload = settings.max_payload_size_mb * 1024 * 1024  # Convert MB to bytes

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old entries (older than 60s)
        request_counts[client_ip] = [
            t for t in request_counts[client_ip] if now - t < 60
        ]

        if len(request_counts[client_ip]) >= max_rpm:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "detail": f"Max {max_rpm} requests/min"},
            )

        # Check payload size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > max_payload:
            return JSONResponse(
                status_code=413,
                content={"error": "payload_too_large", "detail": f"Max {settings.max_payload_size_mb}MB"},
            )

        request_counts[client_ip].append(now)
        return await call_next(request)

    logger.info(" Middleware registered (CORS + rate limiting: %d req/min)", max_rpm)


def _init_rules_engine(app: FastAPI, settings: Any) -> None:
    """
    Initialize the dynamic rules engine and register admin endpoints.
    
    Gracefully degrades:
    - If PostgreSQL unavailable → rules load from JSON configs only
    - Admin API still mounts but DB-dependent endpoints return 503
    """
    from .api.admin_endpoints import admin_router, init_admin
    from .core.formula_engine import FormulaEngine
    from .core.rules_provider import RulesProvider

    rules_db = None
    if settings.rules_db_enabled:
        try:
            from .infrastructure.rules_database import RulesDatabaseAdapter
            rules_db = RulesDatabaseAdapter()
            logger.info(" Rules database adapter initialized")
        except Exception as e:
            logger.warning(f"  Rules DB unavailable (will use JSON fallback): {e}")

    # Always create provider (falls back to JSON configs if no DB)
    formula_engine = FormulaEngine()
    rules_provider = RulesProvider(
        rules_db=rules_db,
        cache_ttl_seconds=settings.rules_cache_ttl_seconds,
    )

    # Wire up admin endpoints
    init_admin(rules_db, rules_provider, formula_engine)
    app.include_router(admin_router)

    # Store on app state for access from other endpoints
    app.state.rules_provider = rules_provider
    app.state.formula_engine = formula_engine

    logger.info(" Dynamic rules engine initialized (DB=%s)", "enabled" if rules_db else "JSON-only")


# ================================================================
# Module-level app instance (for uvicorn and imports)
# ================================================================
app = create_app()
