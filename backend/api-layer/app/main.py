import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.redis import close_redis
from app.middleware.rate_limit_middleware import GeneralRateLimitMiddleware
from app.middleware.request_id_middleware import RequestIdMiddleware
from app.middleware.request_log_middleware import RequestLogMiddleware
from app.services.main_chatbot_client import main_chatbot_client
from app.services.retention_service import retention_cleanup_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    # Create one outbound HTTP client for the whole app so orchestrator calls reuse connections.
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=5.0,
            read=settings.http_timeout_seconds,
            write=10.0,
            pool=5.0,
        ),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    # Inject the lifespan-owned client into the service wrapper used by endpoints.
    main_chatbot_client.set_client(app.state.http_client)
    retention_task = (
        asyncio.create_task(retention_cleanup_loop(), name="retention-cleanup")
        if settings.retention_cleanup_enabled
        else None
    )
    try:
        yield
    finally:
        if retention_task:
            retention_task.cancel()
            with suppress(asyncio.CancelledError):
                await retention_task
    # Close outbound and infrastructure clients during graceful shutdown.
    await main_chatbot_client.aclose()
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(GeneralRateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root():
    return {"service": settings.app_name, "docs": "/docs", "health": "/api/v1/health"}
