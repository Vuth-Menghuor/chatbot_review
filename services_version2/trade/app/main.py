"""Trade Query Service — Application Entrypoint."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Load service-specific environment variables first
# We are at app/main.py, so parent.parent is the project root where .env lives
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import set_service
from app.api.exceptions import (
    DALServiceError,
    InvalidInputError,
    NotFoundError,
    QueryTimeoutError,
)
from app.api.routes import router
from app.core.config import get_settings
from app.services.trade_service import TradeService

settings = get_settings()

# Initialize logging config using our logging module
from app.core.logging import setup_logging

setup_logging("INFO")

logger = logging.getLogger(__name__)

app = FastAPI(
    title="GDCE Trade Query Service",
    description="Query Cambodia trade statistics via DAL API",
    version="1.0.0",
    servers=[{"url": f"http://localhost:{settings.port}", "description": "Local server"}],
)

# Register CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(InvalidInputError)
async def _invalid_input_error(request, exc: InvalidInputError):
    logger.warning(f"Invalid input: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "VALIDATION_ERROR", "message": exc.detail},
    )


@app.exception_handler(NotFoundError)
async def _not_found_error(request, exc: NotFoundError):
    logger.info(f"No results: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "NO_RESULTS", "message": exc.detail},
    )


@app.exception_handler(DALServiceError)
async def _dal_service_error(request, exc: DALServiceError):
    logger.error(f"DAL service error: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "DAL_ERROR", "message": exc.detail},
    )


@app.exception_handler(QueryTimeoutError)
async def _query_timeout_error(request, exc: QueryTimeoutError):
    logger.error(f"Query timeout: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "QUERY_TIMEOUT", "message": exc.detail},
    )


@app.exception_handler(Exception)
async def _general_error(request, exc: Exception):
    logger.error(f"Unhandled: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An internal error occurred.",
        },
    )

# ---------------------------------------------------------------------------
# Startup: wire dependencies
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event():
    logger.info("Trade Query Service starting...")
    service = TradeService()
    set_service(service)
    logger.info("TradeService injected.")

# ---------------------------------------------------------------------------
# Mount routes
# ---------------------------------------------------------------------------

app.include_router(router)
