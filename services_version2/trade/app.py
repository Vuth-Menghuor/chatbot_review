"""Trade Query Service — Application Entrypoint."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pathlib import Path
from dotenv import load_dotenv

# Load service-specific environment variables first
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

from fastapi.middleware.cors import CORSMiddleware
from config import get_settings
from api.endpoints import router, set_service
from api.exceptions import (
    InvalidInputError,
    NotFoundError,
    DALServiceError,
    QueryTimeoutError,
)
from core.exceptions import ValidationError, UnknownIntentError, NoResultsError
from dal.exceptions import DALError
from core.normaliser import NormalisationError
from core.service import TradeService

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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
