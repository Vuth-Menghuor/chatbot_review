"""
API Endpoints for Orchestrator Service
FastAPI route handlers with full integration of validators, formatters, and service coordination
"""

import logging
import uuid
import time
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from .schemas import (
    QueryRequest,
    QueryResponse,
    HealthCheckResponse,
    ErrorResponse,
    Citation,
)
from ..infrastructure.metrics import record_query
from ..infrastructure.cache_service import get_cache_service

# Intents that are safe to cache
_CACHEABLE_INTENTS = {"calculation", "hs_code_lookup", "definition", "general", "policy", "trade_query"}

# TTL per intent (seconds)
_CACHE_TTL = {
    "calculation": 86400,      # 24 hours  — exchange rate refreshes are acceptable at this window
    "hs_code_lookup": 86400,   # 24 hours
    "definition": 172800,      # 48 hours
    "policy": 172800,          # 48 hours
    "trade_query": 86400,      # 24 hours — historical trade data is immutable
    "general": 86400,          # 24 hours
}

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["orchestrator"])


# =====================================================
# DEPENDENCY INJECTION
# =====================================================

async def get_coordinator(request: Request):
    """Get service coordinator (dependency injection)."""
    if not hasattr(request.app.state, 'coordinator'):
        raise HTTPException(
            status_code=500,
            detail="Service coordinator not initialized. Please wait for startup to complete."
        )
    return request.app.state.coordinator


async def get_config(request: Request):
    """Get configuration (dependency injection)."""
    if not hasattr(request.app.state, 'config'):
        raise HTTPException(
            status_code=500,
            detail="Configuration not initialized. Please wait for startup to complete."
        )
    return request.app.state.config


# =====================================================
# ENDPOINTS
# =====================================================


@router.post("/query", response_model=QueryResponse)
async def process_query(
    req: QueryRequest,
    app_request: Request,
    coordinator=Depends(get_coordinator)
) -> QueryResponse:
    """
    Process a user query with full validation and formatting.
    
    Features:
    - Input validation (injection detection, scope checking)
    - Intent detection (calculation, trade_query, definition, etc.)
    - Service coordination and routing
    - Output validation
    - LLM response formatting for improved user experience
    
    Args:
        req: Query request
        app_request: FastAPI request (for app state access)
        coordinator: Service coordinator
        
    Returns:
        Query response with answer, citations, and metadata
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    try:
        question = req.question.strip()
        logger.info(f"[{request_id}] 🔵 Processing query: {question[:80]}...")
        
        # ===== STEP 1: INPUT VALIDATION =====
        if hasattr(app_request.app.state, 'input_validator'):
            input_validator = app_request.app.state.input_validator
            
            # Check for injection/safety
            is_safe, reason = await input_validator.validate_input_async(question)
            if not is_safe and reason != "out_of_scope":
                logger.warning(f"[{request_id}] ⚠️ Security check failed: {reason}")
                latency = (time.time() - start_time) * 1000
                return QueryResponse(
                    request_id=request_id,
                    question=question,
                    answer="I cannot process that request. Please ask a legitimate customs question.",
                    intent="refusal",
                    status="refused",
                    citations=[],
                    latency_ms=latency,
                    metadata={"security": reason}
                )
        
        # ===== STEP 1.5: CACHE LOOKUP =====
        # Check the cache before hitting downstream services.
        # We do a pre-check without knowing the intent yet, keyed only on the
        # normalised question text.  A hit is only returned when the cached
        # result came from a cacheable intent.
        cache_service = get_cache_service()
        cached_result = cache_service.get_cached_response(question)
        if cached_result is not None and cached_result.get("intent") in _CACHEABLE_INTENTS:
            logger.info(
                f"[{request_id}] ⚡ Cache HIT for intent '{cached_result.get('intent')}' "
                f"— skipping downstream services"
            )
            
            # --- Update session context on Cache HIT ---
            if req.session_id:
                try:
                    coordinator.update_session_for_query(
                        session_id=req.session_id,
                        query=question,
                        intent_value=cached_result.get("intent"),
                        answer_summary=cached_result.get("answer", "Query processed")[:200]
                    )
                except Exception as e:
                    logger.warning(f"[{request_id}] Failed to update session context on cache hit: {e}")
            
            latency_ms = (time.time() - start_time) * 1000
            cached_result.setdefault("metadata", {})["cache_hit"] = True
            response = QueryResponse(
                request_id=request_id,
                question=question,
                answer=cached_result.get("answer", "No answer found"),
                intent=cached_result.get("intent", "unclassified"),
                status=cached_result.get("status", "completed"),
                latency_ms=latency_ms,
                metadata=cached_result.get("metadata", {}),
                table=cached_result.get("table"),
                visualization=cached_result.get("visualization"),
                suggestions=cached_result.get("suggestions", []),
                summary_metrics=cached_result.get("summary_metrics"),
            )
            if "citations" in cached_result:
                response.citations = [
                    Citation(**c) if isinstance(c, dict) else c
                    for c in cached_result.get("citations", [])
                ]
            record_query(response.intent, response.status, latency_ms / 1000.0)
            return response
        else:
            logger.info(
                f"[{request_id}] ❌ Cache MISS for query: '{question}' "
                f"— initiating full orchestrator query processing workflow..."
            )
        
        # ===== STEP 2: PROCESS THROUGH COORDINATOR =====
        result = await coordinator.process_query(
            question=question,
            session_id=req.session_id
        )
        result_intent = result.get("intent", "")

        # ===== STEP 3: OUTPUT VALIDATION (optional) =====
        if hasattr(app_request.app.state, 'output_validator') and 'answer' in result and result.get("status") != "failed":
            output_validator = app_request.app.state.output_validator
            is_safe, reason = output_validator.validate_response(result.get('answer', ''))
            if not is_safe:
                logger.warning(f"[{request_id}] ⚠️ Output validation failed: {reason}")
                result['answer'] = "I found a result but it may contain unsafe content. Please rephrase your question."
        

        
        latency_ms = (time.time() - start_time) * 1000
        
        # ===== BUILD RESPONSE =====
        response = QueryResponse(
            request_id=request_id,
            question=question,
            answer=result.get("answer", "No answer found"),
            intent=result.get("intent", "unclassified"),
            status=result.get("status", "completed"),
            latency_ms=latency_ms,
            metadata=result.get("metadata", {}),
            table=result.get("table"),
            visualization=result.get("visualization"),
            suggestions=result.get("suggestions", []),
            summary_metrics=result.get("summary_metrics"),
        )
        
        # Add citations
        if "citations" in result:
            response.citations = [
                Citation(**c) if isinstance(c, dict) else c
                for c in result.get("citations", [])
            ]
        
        # Add clarifications
        if "clarifications" in result:
            response.clarifications = result["clarifications"]
        
        # Add errors
        if "errors" in result:
            response.errors = result["errors"]
        
        # ===== STEP 4.5: POPULATE CACHE =====
        # Store AFTER formatting so the cached answer is the final polished version.
        # Key uses question ONLY (no intent) to match the pre-coordinator lookup above.
        if response.status == "completed" and result_intent in _CACHEABLE_INTENTS:
            ttl = _CACHE_TTL.get(result_intent, 3600)
            # Build a slim, serialisable snapshot of the result for caching
            cache_payload = {
                "intent": result_intent,
                "status": response.status,
                "answer": response.answer,
                "metadata": result.get("metadata", {}),
                "citations": [
                    c.dict() if hasattr(c, "dict") else c
                    for c in response.citations
                ],
                "table": result.get("table"),
                "visualization": result.get("visualization"),
                "suggestions": result.get("suggestions", []),
                "summary_metrics": result.get("summary_metrics"),
            }
            # intent=None → key = hash(question) — same as the lookup above
            cache_service.cache_response(
                question=question,
                response=cache_payload,
                ttl_seconds=ttl,
                source=result_intent,
            )
            logger.info(
                f"[{request_id}] 💾 Successfully stored query results in cache for intent '{result_intent}' "
                f"(TTL: {ttl}s, key: hash(question))"
            )
        
        logger.info(
            f"[{response.request_id}] ✅ Query processed in {response.latency_ms:.1f}ms | "
            f"Intent: {response.intent} | Status: {response.status} | "
            f"Citations: {len(response.citations)}"
        )
        
        # Record metrics
        record_query(response.intent, response.status, latency_ms / 1000.0)
        
        return response

        
    except Exception as e:
        logger.error(f"[{request_id}] ❌ Error processing query: {e}", exc_info=True)
        latency_ms = (time.time() - start_time) * 1000
        
        # Record error metrics
        record_query("error", "failed", latency_ms / 1000.0)
        
        return QueryResponse(
            request_id=request_id,
            question=req.question,
            answer=f"I encountered an error while processing your request: {str(e)}",
            intent="error",
            status="failed",
            citations=[],
            latency_ms=latency_ms,
            metadata={"error": str(e)}
        )


@router.post("/chat", response_model=QueryResponse)
async def chat(req: QueryRequest, app_request: Request, coordinator=Depends(get_coordinator)):
    """
    Chat endpoint (alias for /query).
    
    Provides a familiar REST endpoint name for chat-like interactions.
    
    Args:
        req: Query request (same format as /query)
        app_request: FastAPI request
        coordinator: Service coordinator
        
    Returns:
        Query response (same format as /query)
    """
    return await process_query(req, app_request, coordinator)


@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """
    Quick health check - orchestrator service itself only.
    
    Does NOT check downstream services to keep response fast.
    Use /status for comprehensive health checks.
    
    Returns:
        Health check response indicating service is running
    """
    return HealthCheckResponse(
        status="healthy",
        version="2.0.0",
        timestamp=datetime.utcnow().isoformat(),
        services={}
    )


@router.get("/status", response_model=dict)
async def get_status(config=Depends(get_config)) -> dict:
    """
    Get detailed orchestrator service status.
    
    Returns:
        Service status including configuration and component states
    """
    return {
        "service": "GDCE Orchestrator v2",
        "status": "running",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "configuration": {
            "host": config.host,
            "port": config.port,
            "log_level": config.log_level if hasattr(config, 'log_level') else "INFO",
            "llm_intent_detection": config.llm_intent_detection_enabled if hasattr(config, 'llm_intent_detection_enabled') else False,
        }
    }


@router.get("/info", response_model=dict)
async def get_info():
    """
    Get service information and available endpoints.
    
    Returns:
        Service metadata and capabilities
    """
    return {
        "service": "GDCE Orchestrator",
        "version": "2.0.0",
        "description": "Customs and Trade Query Orchestrator - Routes queries to appropriate services",
        "capabilities": [
            "Customs duty calculation",
            "Trade data querying",
            "HS code lookup and classification",
            "Policy procedures and documentation",
            "Definition and glossary lookup",
            "Answering General Information related to GDCE."
        ],
        "endpoints": {
            "query": {
                "method": "POST",
                "path": "/query",
                "description": "Process a user query"
            },
            "chat": {
                "method": "POST",
                "path": "/chat",
                "description": "Chat endpoint (alias for /query)"
            },
            "health": {
                "method": "GET",
                "path": "/health",
                "description": "Check service health"
            },
            "status": {
                "method": "GET",
                "path": "/status",
                "description": "Get service status"
            },
            "info": {
                "method": "GET",
                "path": "/info",
                "description": "Get service information"
            },
            "docs": {
                "method": "GET",
                "path": "/docs",
                "description": "OpenAPI documentation (Swagger)"
            }
        }
    }

"""
What is does: 
1. Simulates Intent Detection: 
It runs the intent classifier on the question to show what intent 
would be triggered (e.g., calculation, trade_query, definition).

2. Predicts Routing: 
It returns which primary service the query would be sent to (e.g. calculator, 
retrieval, or trade_data).

3. Displays Configuration Debugging: 
Shows if LLM intent detection is enabled or if the policy engine is available.
"""

@router.post("/query/explain", response_model=dict)
async def explain_query(
    req: QueryRequest,
    app_request: Request,
    coordinator=Depends(get_coordinator)
) -> dict:
    """
    Debug endpoint: Explain how a query would be routed and processed.
    
    Useful for understanding intent detection and service routing logic.
    
    Args:
        req: Query request
        app_request: FastAPI request
        coordinator: Service coordinator
        
    Returns:
        Routing explanation including intent, validation, and service routing
    """
    question = req.question.strip()
    request_id = str(uuid.uuid4())
    
    try:
        # Get intent
        intent = coordinator.workflow_executor.detect_intent(question)
        
        # Validate for calculation
        # calculation is the only intent that enforces strict input constraints before routing.
        is_valid_calc, missing = coordinator.workflow_executor.validate_calculation_inputs(question) if intent.value == "calculation" else (True, None)
        
        return {
            "request_id": request_id,
            "question": question,
            "intent": intent.value,
            "intent_confidence": "high" if intent.value != "unclassified" else "low",
            "validation": {
                "is_calculation_valid": is_valid_calc,
                "missing_fields": missing or []
            },
            "intended_workflow": {
                "primary_service": "calculator" if intent.value == "calculation" else "general" if intent.value == "general" else "trade_data" if intent.value == "trade_query" else "retrieval",
                "validation_required": True,
                "output_formatting": True
            },
            "debug_info": {
                "llm_enabled": coordinator.workflow_executor.use_llm_intent,
                "policy_engine_available": coordinator.policy_engine is not None
            }
        }
    except Exception as e:
        logger.error(f"Error explaining query: {e}")
        return {
            "request_id": request_id,
            "question": question,
            "error": str(e),
            "error_type": type(e).__name__
        }


@router.get("/", response_model=dict)
async def root():
    """Root endpoint - service information."""
    return {
        "service": "GDCE Orchestrator v2",
        "version": "2.0.0",
        "port": 8001,
        "status": "online",
        "endpoints": {
            "health": "GET /health",
            "status": "GET /status",
            "query": "POST /query",
            "explain": "POST /query/explain",
            "swagger": "/docs",
            "openapi": "/openapi.json"
        },
        "description": "Main API entry point - routes queries to appropriate microservices",
        "docs": "/docs",
        "health": "/health"
    }
