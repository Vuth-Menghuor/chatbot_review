"""
Health Check Routes - Orchestrator service

Dedicated health and readiness endpoints separated from the main
business-logic router so they can be mounted at a distinct prefix
or remain at root level without being mixed with query endpoints.

Endpoints:
    GET /health  — lightweight liveness probe (no downstream I/O)
    GET /ready   — readiness probe (checks coordinator & first-layer)
    GET /status  — detailed dependency status (Redis, Postgres, etc.)
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Request

from ..schemas.schemas import HealthCheckResponse
from ..infrastructure.health_checks import check_redis_health, check_postgres_health

logger = logging.getLogger(__name__)

health_router = APIRouter(tags=["health"])


@health_router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """
    Liveness probe — orchestrator process only.

    Does NOT call any downstream service so the response is always fast.
    Use ``GET /ready`` or ``GET /status`` when you need a deeper check.

    Returns:
        HealthCheckResponse with status "healthy".
    """
    return HealthCheckResponse(
        status="healthy",
        version="2.0.0",
        timestamp=datetime.utcnow().isoformat() + "Z",
        services={},
    )


@health_router.get("/ready", response_model=Dict[str, Any])
async def readiness_check(request: Request) -> Dict[str, Any]:
    """
    Readiness probe — checks whether core in-process components are available.

    Verifies that the ``coordinator`` and ``first_layer_service`` have been
    initialised on ``app.state``.  Returns HTTP 200 when ready; the caller
    can inspect ``ready`` in the body for a boolean result.

    Returns:
        JSON dict with ``ready``, ``checks``, and ``timestamp`` fields.
    """
    checks: Dict[str, bool] = {}

    checks["coordinator"] = hasattr(request.app.state, "coordinator")
    checks["first_layer_service"] = hasattr(request.app.state, "first_layer_service")
    checks["input_validator"] = hasattr(request.app.state, "input_validator")

    ready = all(checks.values())

    return {
        "ready": ready,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@health_router.get("/status", response_model=Dict[str, Any])
async def get_status(request: Request) -> Dict[str, Any]:
    """
    Detailed dependency status — checks Redis, Postgres, and service config.

    Intended for ops dashboards and CI smoke tests.  Slightly slower than
    ``/health`` because it performs real I/O against external dependencies.

    Returns:
        JSON dict with per-dependency statuses and current configuration.
    """
    config = getattr(request.app.state, "config", None)

    # --- Redis ---
    redis_status = "unavailable"
    if hasattr(request.app.state, "first_layer_service"):
        try:
            redis_client = request.app.state.first_layer_service.session_manager.redis_client
            redis_status = check_redis_health(redis_client)
        except Exception as exc:
            logger.warning("Redis health check failed: %s", exc)
            redis_status = "error"

    # --- Postgres ---
    postgres_status = "unavailable"
    if config is not None:
        try:
            postgres_status = check_postgres_health(config)
        except Exception as exc:
            logger.warning("Postgres health check failed: %s", exc)
            postgres_status = "error"

    # --- Configuration snapshot ---
    config_snapshot: Dict[str, Any] = {}
    if config is not None:
        config_snapshot = {
            "host": getattr(config, "host", "unknown"),
            "port": getattr(config, "port", "unknown"),
            "log_level": getattr(config, "log_level", "INFO"),
            "llm_intent_detection": getattr(config, "llm_intent_detection_enabled", False),
        }

    return {
        "service": "GDCE Orchestrator v2",
        "status": "running",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "dependencies": {
            "redis": redis_status,
            "postgres": postgres_status,
        },
        "configuration": config_snapshot,
    }
