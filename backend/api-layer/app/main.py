from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
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
