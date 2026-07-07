"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import router as v1_router
from app.core.cache import close_redis
from app.core.config import get_settings
from app.core.errors import DALError
from app.core.logging import setup_logging
from app.core.middleware import register_middleware
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.db.metadata_session import close_metadata_engine
from app.db.operational_session import close_operational_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle hooks."""
    setup_logging()
    yield
    # Cleanup
    await close_redis()
    await close_metadata_engine()
    await close_operational_engine()


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="DAL — Data Access Layer",
        description=(
            "Metadata-driven query API that provides secure, governed access "
            "to operational data. Supports dynamic dimensions, measures, "
            "period filtering, and caching."
        ),
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    # --- SlowAPI rate-limiting middleware ---
    app.state.limiter = limiter
    # app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request, exc: RateLimitExceeded):
        return rate_limit_exceeded_handler(request, exc)
    app.add_middleware(SlowAPIMiddleware)

    # Register custom middleware (request ID, timing, error handling)
    register_middleware(app)

    # Custom exception handler for DALError
    @app.exception_handler(DALError)
    async def dal_error_handler(request, exc: DALError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "request_id": getattr(request.state, "request_id", "unknown"),
                "error": {
                    "code": exc.error_code.value,
                    "message": exc.error_message,
                },
            },
        )

    # Include routers
    app.include_router(v1_router)

    return app


app = create_app()

