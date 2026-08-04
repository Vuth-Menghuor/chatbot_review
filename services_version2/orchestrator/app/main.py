"""
FastAPI Application - Orchestrator service v2
Main application setup and middleware configuration
"""

import logging
import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from .core.logging import setup_structured_logging, get_logger
from .core.middleware import RequestLoggingMiddleware
from .core.config import get_config, FormatterServiceConfig, LLMFirstLayerConfig
from .services import ServiceCoordinator
from .ai.summarizer import get_formatter_service
from .ai import get_llm_first_layer_service
from .api import router as api_router
from .ai.shims.validator_service import get_input_validator, get_output_validator
from .infrastructure import (
    ServiceClientFactory,
    initialize_service_clients,
    get_health_check_service,
    initialize_health_check_service,
    get_service_registry,
)
from .infrastructure.cache_service import get_cache_service

# Import trade query adapter (obsolete cross-service ref, service now accessed via HTTP)
get_trade_query_client = None
PostgresTradeQueryConfig = None

# Configure logging
# Setup structured logging
setup_structured_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    # Get configuration
    config = get_config()
    
    # Create app
    app = FastAPI(
        title="GDCE Orchestrator",
        description="Customs and Trade Query Orchestrator - Routes queries to appropriate services",
        version="2.0.0",
        servers=[{"url": "http://localhost:8001", "description": "Local server"}],
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    
    # Store config in app state
    app.state.config = config
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add request logging and correlation ID middleware
    app.add_middleware(RequestLoggingMiddleware)
    
    # Initialize services on startup
    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup."""
        import sys
        # Force standard logging to propagate to stdout
        root_logger = logging.getLogger()
        for h in list(root_logger.handlers):
            if isinstance(h, logging.StreamHandler):
                root_logger.removeHandler(h)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        # Re-enable standard loggers disabled by uvicorn's logging setup
        for name, logger_obj in logging.root.manager.loggerDict.items():
            if isinstance(logger_obj, logging.Logger):
                logger_obj.disabled = False
                logger_obj.propagate = True

        logger.info("Starting orchestrator service v2...")
        logger.info("=" * 60)
        
        try:
            # Initialize validators
            logger.info("[1/7] Initializing input validators...")
            input_validator = get_input_validator()
            output_validator = get_output_validator()
            app.state.input_validator = input_validator
            app.state.output_validator = output_validator
            logger.info("[OK] Validators initialized")
            
            # Initialize LLM Formatter (Gemini as primary)
            logger.info("[2/7] Initializing LLM_Formatter (Gemini)...")
            formatter_config = FormatterServiceConfig(
                provider="gemini",
                gemini_api_key=config.gemini_api_key if hasattr(config, 'gemini_api_key') else os.getenv("GEMINI_API_KEY", ""),
                gemini_model=config.gemini_model if hasattr(config, 'gemini_model') else "gemini-3.1-flash-lite",
                timeout=config.gemini_timeout if hasattr(config, 'gemini_timeout') else 30,
                enabled=True
            )
            formatter = get_formatter_service(formatter_config)
            app.state.formatter = formatter
            logger.info(f"[OK] LLM_Formatter initialized (Available: {formatter.is_available()})")
            
            # Initialize PostgreSQL trade query client
            logger.info("[3/7] Initializing PostgreSQL trade query client...")
            if PostgresTradeQueryConfig and get_trade_query_client:
                try:
                    pg_config = PostgresTradeQueryConfig(
                        host=config.qdrant_host if hasattr(config, 'pg_host') else os.getenv("PG_HOST"),
                        port=5432,
                        database=os.getenv("PG_DATABASE", "gdce_hs_code"),
                        user=os.getenv("PG_USER", "postgres"),
                        password=os.getenv("PG_PASSWORD", "")
                    )
                    trade_client = get_trade_query_client(pg_config)
                    app.state.trade_query_client = trade_client
                    logger.info(f"[OK] PostgreSQL trade client initialized (Available: {trade_client.is_available()})")
                    logger.warning("[WARN] Orchestrator has direct database access - consider migrating to HTTP calls to trade_query service")
                except Exception as e:
                    logger.warning(f"Failed to initialize PostgreSQL trade client: {e}")
                    app.state.trade_query_client = None
            else:
                logger.warning("Trade query adapter not available - trade data queries may be limited")
                app.state.trade_query_client = None
            
            # Initialize service clients
            logger.info("[4/7] Initializing service clients...")
            await initialize_service_clients(config)
            logger.info("[OK] Service clients initialized")
            
            policy_engine = None
            
            # Initialize unified LLM_first_layer service
            logger.info("[6/7] Initializing unified LLM_first_layer service...")
            first_layer_config = LLMFirstLayerConfig(
                gemini_api_key=config.gemini_api_key if hasattr(config, 'gemini_api_key') else os.getenv("GEMINI_API_KEY", ""),
                gemini_model=config.gemini_model if hasattr(config, 'gemini_model') else "gemini-3.1-flash-lite",
                gemini_timeout=config.gemini_timeout if hasattr(config, 'gemini_timeout') else 30,
                enable_validation=True,
                enable_intent_detection=True,
                enable_ask_back=True,
                enable_currency_detection=True,
                enable_rewriting=True,
            )
            first_layer_service = get_llm_first_layer_service(first_layer_config)
            app.state.first_layer_service = first_layer_service
            logger.info("[OK] LLM_first_layer service initialized")

            # Set the Gemini client on input_validator for LLM validation
            try:
                llm_service = first_layer_service._get_llm_service()
                gemini_provider = llm_service.router.providers.get("gemini")
                if gemini_provider and gemini_provider.client:
                    input_validator.set_client(gemini_provider.client)
                    logger.info("[OK] Input validator LLM client bound")
            except Exception as e:
                logger.warning(f"Could not bind LLM client to input validator: {e}")
            
            # Initialize service coordinator
            from .infrastructure import get_service_registry
            registry = get_service_registry()
            
            coordinator = ServiceCoordinator(
                retrieval_client=registry.get("retrieval"),
                general_client=registry.get("general"),
                calculator_client=registry.get("calculator"),
                trade_data_client=registry.get("trade_data"),
                policy_engine=policy_engine,
                formatter_service=formatter,
                first_layer_service=first_layer_service,
                gemini_api_key=config.gemini_api_key,
            )
            
            app.state.coordinator = coordinator
            app.state.policy_engine = policy_engine
            
            logger.info("[OK] Service coordinator initialized")
            
            # Initialize cache service (STEP 8)
            logger.info("[5.5/6] Initializing cache service (STEP 8)...")
            from .infrastructure.cache_service import get_cache_service
            # Update cache to hybrid (memory + redis) for horizontal scaling
            cache_level = config.cache_level if hasattr(config, 'cache_level') else os.getenv("CACHE_LEVEL", "hybrid")
            cache_service = get_cache_service(level=cache_level, max_size=5000)
            app.state.cache = cache_service
            logger.info(f"[OK] Cache service initialized (Level: {cache_level}, Memory: 5000 max entries)")
    
            
            # Initialize health check service
            logger.info("[7/7] Initializing health check service...")
            health_check_service = initialize_health_check_service(
                check_timeout_sec=5,
                failure_threshold=3,
                degraded_response_time_ms=1000.0
            )
            app.state.health_check_service = health_check_service
            logger.info("[OK] Health check service initialized")
            
            # Start background health check task
            logger.info("[Starting] Background health check task (120-second interval)...")
            
            async def periodic_health_check():
                """Periodically check service health."""
                logger.info("Background health check task started")
                while True:
                    try:
                        await asyncio.sleep(120)  
                        
                        # Get all registered service clients
                        service_clients = {}
                        if registry.get("retrieval"):
                            service_clients["retrieval"] = registry.get("retrieval")
                        if registry.get("general"):
                            service_clients["general"] = registry.get("general")
                        if registry.get("calculator"):
                            service_clients["calculator"] = registry.get("calculator")
                        if registry.get("trade_data"):
                            service_clients["trade_data"] = registry.get("trade_data")
                        
                        if service_clients:
                            # Run health checks
                            system_health = await health_check_service.check_all_services(service_clients)
                            
                            # Log health status
                            status_line = f"[HealthCheck] System: {system_health.overall_status.value} | Readiness: {system_health.readiness.value}"
                            
                            for name, health in system_health.services.items():
                                status_line += f" | {name}: {health.status.value}"
                            
                            logger.info(status_line)
                    
                    except Exception as e:
                        logger.error(f"Error in background health check: {e}")
            
            # Start health check task
            asyncio.create_task(periodic_health_check())
            
            logger.info("[OK] Background health check task started")

            # Initialize PostgreSQL chatbot database and apply migrations
            try:
                from .infrastructure import check_and_create_db
                check_and_create_db()
                
                from alembic.config import Config
                from alembic import command
                from pathlib import Path
                ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
                alembic_cfg = Config(str(ini_path))
                alembic_cfg.set_main_option("programmatic", "true")
                await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
                logger.info("[OK] Main Chatbot DB checked, created, and migrated successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize and migrate chatbot database: {e}")


            
            logger.info("=" * 60)
            logger.info(f"[READY] Orchestrator v2.0 Ready")
            logger.info(f"   Listening on {config.host}:{config.port}")
            logger.info(f"   API Docs: http://{config.host}:{config.port}/docs")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"[ERR] Startup error: {e}")
            logger.error("=" * 60)
            raise
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Clean up on shutdown."""
        logger.info("Shutting down orchestrator service v2...")
        
        try:
            from .infrastructure import get_service_registry
            registry = get_service_registry()
            await registry.close_all()
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
    
    # Include API routes
    app.include_router(api_router)
    
    # Expose Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
    
    # Root endpoint
    @app.get("/", response_model=dict)
    async def root():
        """Root endpoint."""
        return {
            "service": "GDCE Orchestrator v2",
            "status": "running",
            "docs": "/docs",
            "api_version": "2.0.0"
        }
    
    # Enhanced health check endpoint (liveness probe)
    @app.get("/health", response_model=dict)
    async def health():
        """
        Health check endpoint (liveness probe for K8s/Docker).
        
        Returns basic service health and circuit breaker status.
        """
        health_service = get_health_check_service()
        last_health = health_service.get_last_health()
        
        if last_health:
            return {
                "status": last_health.overall_status.value,
                "service": "GDCE Orchestrator v2",
                "version": "2.0.0",
                "readiness": last_health.readiness.value,
                "services": {
                    name: {
                        "status": health.status.value,
                        "circuit_state": health.circuit_state,
                        "response_time_ms": health.response_time_ms
                    }
                    for name, health in last_health.services.items()
                }
            }
        else:
            # If no health check has been performed yet
            return {
                "status": "unknown",
                "service": "GDCE Orchestrator v2",
                "version": "2.0.0",
                "message": "Waiting for first health check"
            }
    
    # Readiness endpoint (readiness probe for K8s/Docker)
    @app.get("/ready", response_model=dict)
    async def readiness():
        """
        Readiness probe - indicates if service can handle traffic.
        
        Returns 200 if all critical services are available.
        Returns 503 if any service is down.
        """
        health_service = get_health_check_service()
        last_health = health_service.get_last_health()
        
        if not last_health:
            # If no health check has been performed, assume ready
            return {
                "ready": True,
                "message": "Service ready (first check pending)"
            }
        
        if last_health.readiness.value == "ready":
            return {
                "ready": True,
                "readiness": last_health.readiness.value,
                "details": {
                    name: health.status.value
                    for name, health in last_health.services.items()
                }
            }
        else:
            # Service not ready
            return {
                "ready": False,
                "readiness": last_health.readiness.value,
                "details": {
                    name: health.status.value
                    for name, health in last_health.services.items()
                }
            }
    
    # Admin debug endpoint for health status
    @app.get("/admin/health/status", response_model=dict)
    async def admin_health_status():
        """Admin endpoint for detailed health information."""
        health_service = get_health_check_service()
        last_health = health_service.get_last_health()
        
        if not last_health:
            return {"error": "No health checks performed yet"}
        
        return {
            "timestamp": last_health.timestamp.isoformat(),
            "overall_status": last_health.overall_status.value,
            "readiness": last_health.readiness.value,
            "services": {
                name: health.to_dict()
                for name, health in last_health.services.items()
            },
            "metadata": last_health.metadata,
            "metrics": health_service.get_health_metrics(),
            "recent_errors": health_service.get_error_history(limit=10)
        }
    
    # Admin debug endpoint for error history
    @app.get("/admin/health/errors", response_model=dict)
    async def admin_health_errors():
        """Admin endpoint for error history."""
        health_service = get_health_check_service()
        return {
            "recent_errors": health_service.get_error_history(limit=50),
            "error_count": len(health_service.error_history)
        }
    
    # Admin endpoint for cache statistics (STEP 8)
    @app.get("/admin/cache-stats", response_model=dict)
    async def admin_cache_stats():
        """
        Admin endpoint for cache statistics and performance metrics.
        Useful for monitoring cache hit rates and effectiveness.
        """
        cache_service = get_cache_service()
        stats = cache_service.get_cache_stats()
        
        return {
            "cache_stats": stats,
            "interpretation": {
                "memory_size": stats.get("memory", {}).get("size", 0),
                "memory_max": stats.get("memory", {}).get("max_size", 0),
                "total_hits": stats.get("memory", {}).get("total_hits", 0),
                "avg_hits_per_entry": round(stats.get("memory", {}).get("avg_hits_per_entry", 0), 2),
                "memory_usage_mb": round(stats.get("memory", {}).get("memory_usage_mb", 0), 2),
                "cache_level": stats.get("level", "memory"),
                "note": "HS codes: 24h TTL, Definitions: 48h TTL, Cache hits provide 400-500ms latency savings per request"
            }
        }
    
    # Admin endpoint for human-readable metrics summary
    @app.get("/admin/metrics/summary", response_model=dict)
    async def admin_metrics_summary():
        """
        Admin endpoint for human-readable metrics summary.
        Useful for quick checks without needing a Prometheus/Grafana server.
        """
        from prometheus_client import REGISTRY
        
        summary = {
            "query_counts": {},
            "query_durations_avg_sec": {},
            "service_errors": {},
            "cache": {"hits": 0, "misses": 0}
        }
        
        for metric in REGISTRY.collect():
            if metric.name == 'gdce_query_count':
                for sample in metric.samples:
                    if sample.name.endswith('_total'):
                        intent = sample.labels.get('intent', 'unknown')
                        status = sample.labels.get('status', 'unknown')
                        key = f"{intent} ({status})"
                        summary["query_counts"][key] = sample.value
                    
            elif metric.name == 'gdce_query_duration_seconds':
                sums = {}
                counts = {}
                for sample in metric.samples:
                    intent = sample.labels.get('intent', 'unknown')
                    if sample.name.endswith('_sum'):
                        sums[intent] = sample.value
                    elif sample.name.endswith('_count'):
                        counts[intent] = sample.value
                
                for intent in counts:
                    if counts[intent] > 0:
                        summary["query_durations_avg_sec"][intent] = round(sums[intent] / counts[intent], 4)
                        
            elif metric.name == 'gdce_service_errors':
                for sample in metric.samples:
                    if sample.name.endswith('_total'):
                        service = sample.labels.get('service_name', 'unknown')
                        error = sample.labels.get('error_type', 'unknown')
                        key = f"{service} - {error}"
                        summary["service_errors"][key] = sample.value
                    
            elif metric.name == 'gdce_cache_hits':
                for sample in metric.samples:
                    if sample.name.endswith('_total'):
                        summary["cache"]["hits"] += sample.value
                    
            elif metric.name == 'gdce_cache_misses':
                for sample in metric.samples:
                    if sample.name.endswith('_total'):
                        summary["cache"]["misses"] += sample.value
                    
        return summary
    
    # Deprecated: Old simple health endpoint (kept for backward compatibility)
    @app.get("/health/simple", response_model=dict)
    async def health_simple():
        """Simple health check (deprecated, use /health instead)."""
        return {
            "status": "healthy",
            "service": "GDCE Orchestrator v2",
            "version": "2.0.0"
        }
    
    # Error handlers
    @app.exception_handler(ValueError)
    async def value_error_handler(request, exc):
        """Handle validation errors."""
        return JSONResponse(
            status_code=400,
            content={
                "error": "Validation error",
                "error_code": "VALIDATION_ERROR",
                "details": str(exc)
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        """Handle general exceptions."""
        logger.error(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "details": str(exc) if os.getenv("DEBUG", "false").lower() == "true" else None
            }
        )
    
    return app


# Create app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn
    
    config = get_config()
    uvicorn.run(
        "app:app",
        host=config.host,
        port=config.port,
        reload=config.reload,
        workers=config.workers,
        log_level=config.log_level.lower(),
    )
