"""Request-level middleware: request ID, timing, and error handling."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import DALError
from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


def register_middleware(app: FastAPI) -> None:
    """Attach all middleware to the FastAPI app."""

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Inject request_id, measure latency, handle unhandled errors."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except DALError as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            if settings.is_production:
                logger.error(
                    "Request failed",
                    extra={
                        "request_id": request_id,
                        "error_code": exc.error_code.value,
                        "latency_ms": latency_ms,
                    },
                )
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "request_id": request_id,
                    "error": {
                        "code": exc.error_code.value,
                        "message": exc.error_message,
                    },
                },
            )
        except Exception:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            if settings.is_production:
                logger.exception(
                    "Unhandled error",
                    extra={"request_id": request_id, "latency_ms": latency_ms},
                )
            return JSONResponse(
                status_code=500,
                content={
                    "request_id": request_id,
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                    },
                },
            )

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Latency-Ms"] = str(latency_ms)

        # Store latency for audit logging downstream
        request.state.latency_ms = latency_ms
        if not settings.is_production:
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                },
            )
        return response
