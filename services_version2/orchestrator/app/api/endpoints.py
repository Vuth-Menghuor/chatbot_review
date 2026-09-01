"""
API Endpoints for Orchestrator Service
FastAPI route handlers with full integration of validators, formatters, and service coordination
"""

import asyncio
import json
import logging
import uuid
import time
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse
from ..schemas.schemas import (
    QueryRequest,
    QueryResponse,
    Citation,
)
from app.infrastructure import (
    get_db,
    get_db_context,
    session_id_var,
    message_id_var,
    ChatSession,
    ChatMessage,
    ChatFeedback,
    ChatAttachment,
)
from app.services.db_service import ChatbotDBService
from ..core.logging import get_request_id


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

# Per-session lock table for single-process deployment.
# In multi-worker deployments, the coordinator uses a Redis distributed lock
# instead; this dict is the fallback when Redis is unavailable.
_session_locks: dict = {}


# DEPENDENCY INJECTION

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


# ENDPOINTS


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
    request_id = get_request_id() or str(uuid.uuid4())
    start_time = time.time()
    
    # Auto-generate a session_id if the client did not supply one.
    # This ensures multi-turn context (ask-back → clarification) works reliably.
    effective_session_id = req.session_id or str(uuid.uuid4())
    
    # Initialize session_id_var context variable
    session_id_var.set(effective_session_id)
    
    try:
        question = req.question.strip().strip("`'\" \t\n\r")
        logger.info(f"[{request_id}] [QUERY] Processing query: {question[:80]}...")
        
        # Record user message in DB
        user_msg_id = None
        try:
            with get_db_context() as db:
                ChatbotDBService.sync_get_or_create_session(
                    db=db,
                    session_id=effective_session_id,
                    user_id=req.user_id,
                    project_id=req.project_id
                )
                user_msg = ChatbotDBService.sync_save_chat_message(
                    db=db,
                    session_id=effective_session_id,
                    role="user",
                    content=question
                )
                user_msg_id = user_msg.id
                message_id_var.set(user_msg_id)
        except Exception as db_err:
            logger.error(f"[{request_id}] Failed to record user message: {db_err}")

        
        # Pre-warm unified cache to reduce LLM calls to exactly 1
        session_context = None
        if hasattr(app_request.app.state, 'first_layer_service'):
            try:
                session_mgr = app_request.app.state.first_layer_service.session_manager
                session_context = session_mgr.get_or_create_session(effective_session_id)
                await app_request.app.state.first_layer_service.get_unified_result(question, session_context)
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to pre-warm unified cache: {e}")

        # ===== STEP 1: INPUT VALIDATION =====
        if hasattr(app_request.app.state, 'input_validator'):
            input_validator = app_request.app.state.input_validator
            
            # Check for injection/safety
            is_safe, reason = await input_validator.validate_input_async(question, session_context)
            if not is_safe and reason != "out_of_scope":
                logger.warning(f"[{request_id}] [WARN] Security check failed: {reason}")
                latency = (time.time() - start_time) * 1000
                refusal_msg = "I cannot process that request. Please ask a legitimate customs question."
                return QueryResponse(
                    request_id=request_id,
                    question=question,
                    answer=refusal_msg,
                    message=refusal_msg,
                    intent="refusal",
                    status="refused",
                    citations=[],
                    suggestion=[],
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
                f"[{request_id}] [CACHE_HIT] Cache HIT for intent '{cached_result.get('intent')}' "
                f"— skipping downstream services"
            )
            
            # --- Update session context on Cache HIT ---
            try:
                coordinator.update_session_for_query(
                    session_id=effective_session_id,
                    query=question,
                    intent_value=cached_result.get("intent"),
                    answer_summary=cached_result.get("answer", "Query processed")[:200]
                )
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to update session context on cache hit: {e}")
            
            latency_ms = (time.time() - start_time) * 1000
            cached_result.setdefault("metadata", {})["cache_hit"] = True
            suggestions_list = cached_result.get("suggestions", []) or cached_result.get("suggestion", []) or []
            response = QueryResponse(
                request_id=request_id,
                session_id=effective_session_id,
                question=question,
                answer=cached_result.get("answer", "No answer found"),
                message=cached_result.get("answer", "No answer found"),
                intent=cached_result.get("intent", "unclassified"),
                status=cached_result.get("status", "completed"),
                latency_ms=latency_ms,
                metadata=cached_result.get("metadata", {}),
                table=cached_result.get("table"),
                visualization=cached_result.get("visualization"),
                suggestion=suggestions_list,
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
                f"[{request_id}] [CACHE_MISS] Cache MISS for query: '{question}' "
                f"— initiating full orchestrator query processing workflow..."
            )
        
        # ===== STEP 2: PROCESS THROUGH COORDINATOR =====
        result = await coordinator.process_query(
            question=question,
            session_id=effective_session_id
        )
        result_intent = result.get("intent", "")

        # ===== STEP 3: OUTPUT VALIDATION (optional) =====
        if hasattr(app_request.app.state, 'output_validator') and 'answer' in result and result.get("status") != "failed":
            output_validator = app_request.app.state.output_validator
            is_safe, reason = output_validator.validate_response(result.get('answer', ''))
            if not is_safe:
                logger.warning(f"[{request_id}] [WARN] Output validation failed: {reason}")
                result['answer'] = "I found a result but it may contain unsafe content. Please rephrase your question."
        

        
        latency_ms = (time.time() - start_time) * 1000
        
        # ===== BUILD RESPONSE =====
        suggestions_list = result.get("suggestions", []) or result.get("suggestion", []) or []
        response = QueryResponse(
            request_id=request_id,
            session_id=effective_session_id,
            question=question,
            answer=result.get("answer", "No answer found"),
            message=result.get("answer", "No answer found"),
            intent=result.get("intent", "unclassified"),
            status=result.get("status", "completed"),
            latency_ms=latency_ms,
            metadata=result.get("metadata", {}),
            table=result.get("table"),
            visualization=result.get("visualization"),
            suggestion=suggestions_list,
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
                "message": response.answer,
                "metadata": result.get("metadata", {}),
                "citations": [
                    c.dict() if hasattr(c, "dict") else c
                    for c in response.citations
                ],
                "table": result.get("table"),
                "visualization": result.get("visualization"),
                "suggestion": response.suggestion,
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
                f"[{request_id}] [CACHE_STORED] Successfully stored query results in cache for intent '{result_intent}' "
                f"(TTL: {ttl}s, key: hash(question))"
            )
        
        logger.info(
            f"[{response.request_id}] [SUCCESS] Query processed in {response.latency_ms:.1f}ms | "
            f"Intent: {response.intent} | Status: {response.status} | "
            f"Citations: {len(response.citations)}"
        )
        
        # Record assistant response
        try:
            with get_db_context() as db:
                assistant_content = response.answer or "I was unable to generate a response for your query."
                ChatbotDBService.sync_save_chat_message(
                    db=db,
                    session_id=effective_session_id,
                    role="assistant",
                    content=assistant_content
                )
        except Exception as db_err:
            logger.error(f"[{request_id}] Failed to record assistant response: {db_err}")

        return response

        
    except Exception as e:
        logger.error(f"[{request_id}] [ERROR] Error processing query: {e}", exc_info=True)
        latency_ms = (time.time() - start_time) * 1000
        
        # Record error metrics
        record_query("error", "failed", latency_ms / 1000.0)
        
        # Record assistant error response to DB
        try:
            with get_db_context() as db:
                ChatbotDBService.sync_save_chat_message(
                    db=db,
                    session_id=effective_session_id,
                    role="assistant",
                    content=f"I encountered an error while processing your request: {str(e)}"
                )
        except Exception as db_err:
            logger.error(f"[{request_id}] Failed to record assistant error: {db_err}")

        err_msg = f"I encountered an error while processing your request: {str(e)}"
        return QueryResponse(
            request_id=request_id,
            question=req.question,
            answer=err_msg,
            message=err_msg,
            intent="error",
            status="failed",
            citations=[],
            suggestion=[],
            latency_ms=latency_ms,
            metadata={"error": str(e)}
        )


@router.post("/query/stream")
async def stream_query(
    req: QueryRequest,
    app_request: Request,
    coordinator=Depends(get_coordinator),
):
    """
    Stream a response for a user query using Server-Sent Events (SSE).

    Event types emitted:
      - ``data``          — incremental text chunks from the formatter
      - ``clarification`` — the bot needs more info (no formatter invoked)
      - ``done``          — stream finished, includes final metadata JSON
      - ``error``         — mid-stream failure after partial output
      - ``: keep-alive``  — SSE comment line sent every ~15 s while retrieving

    Session persistence (Redis/Postgres) is written after the ``done`` event.
    Partial responses from disconnected sessions are never persisted.
    """
    request_id = get_request_id() or str(uuid.uuid4())
    effective_session_id = req.session_id or str(uuid.uuid4())
    
    # Initialize session_id_var context variable
    session_id_var.set(effective_session_id)

    async def event_generator():
        # ── 1. Capture ContextVar cache so it survives await boundaries ──────
        from ..ai.analyzer import unified_result_var
        question = req.question.strip().strip("`'\" \t\n\r")

        # Record user message in DB
        user_msg_id = None
        try:
            with get_db_context() as db:
                ChatbotDBService.sync_get_or_create_session(
                    db=db,
                    session_id=effective_session_id,
                    user_id=req.user_id,
                    project_id=req.project_id
                )
                user_msg = ChatbotDBService.sync_save_chat_message(
                    db=db,
                    session_id=effective_session_id,
                    role="user",
                    content=question
                )
                user_msg_id = user_msg.id
                message_id_var.set(user_msg_id)
        except Exception as db_err:
            logger.error(f"[{request_id}] Failed to record user stream message: {db_err}")


        # Pre-warm unified NLU cache (same as /query endpoint)
        cached_nlu = None
        if hasattr(app_request.app.state, 'first_layer_service'):
            try:
                first_layer = app_request.app.state.first_layer_service
                session_mgr = first_layer.session_manager
                sess_ctx = session_mgr.get_or_create_session(effective_session_id)
                await first_layer.get_unified_result(question, sess_ctx)
                cached_nlu = unified_result_var.get()
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to pre-warm NLU cache for streaming: {e}")

        # Restore the ContextVar so downstream code that reads it after any
        # await boundary still finds the cached result.
        if cached_nlu is not None:
            unified_result_var.set(cached_nlu)

        # ── 2. Acquire per-session lock ───────────────────────────────────────
        # Use Redis distributed lock when available; fall back to asyncio.Lock.
        redis_lock = None
        local_lock = None
        try:
            redis_client = getattr(app_request.app.state, 'redis_client', None)
            if redis_client is not None:
                redis_lock = redis_client.lock(
                    f"lock:session:{effective_session_id}", timeout=120
                )
                await asyncio.get_event_loop().run_in_executor(None, redis_lock.acquire)
            else:
                if effective_session_id not in _session_locks:
                    _session_locks[effective_session_id] = asyncio.Lock()
                local_lock = _session_locks[effective_session_id]
                await local_lock.acquire()
        except Exception as lock_err:
            logger.warning(f"[{request_id}] Session lock acquisition failed (continuing without lock): {lock_err}")

        try:
            # ── 3. Safety check ───────────────────────────────────────────────
            if hasattr(app_request.app.state, 'input_validator'):
                try:
                    is_safe, reason = await app_request.app.state.input_validator.validate_input_async(
                        question, None
                    )
                    if not is_safe and reason != "out_of_scope":
                        yield f"data: {json.dumps({'error': 'Request refused by safety filter.', 'reason': reason})}\n\n"
                        return
                except Exception as e:
                    logger.warning(f"[{request_id}] Safety check failed in stream mode: {e}")

            # ── 4. Run coordinator (retrieval/routing) with keep-alive pings ─
            retrieval_task = asyncio.create_task(
                coordinator.process_query(
                    question=question,
                    session_id=effective_session_id,
                    stream=True,
                )
            )

            context_result = None
            while not retrieval_task.done():
                try:
                    context_result = await asyncio.wait_for(
                        asyncio.shield(retrieval_task), timeout=15.0
                    )
                except asyncio.TimeoutError:
                    # Retrieval still running — send SSE keep-alive comment
                    yield ": keep-alive\n\n"
                    # Check for client disconnect while waiting
                    if await app_request.is_disconnected():
                        retrieval_task.cancel()
                        logger.info(f"[{request_id}] Client disconnected during retrieval; task cancelled.")
                        return

            if context_result is None:
                context_result = retrieval_task.result()

            # ── 5. Handle clarification / ask-back path ───────────────────────
            result_status = context_result.get("status", "")
            if result_status == "clarification_required" or context_result.get("clarifications"):
                clarification_payload = {
                    "questions": context_result.get("clarifications", []),
                    "session_id": effective_session_id,
                    "status": "clarification_required",
                    "intent": context_result.get("intent", "unclassified"),
                }
                yield f"event: clarification\ndata: {json.dumps(clarification_payload)}\n\n"
                return

            # For pre-resolved statuses (small_talk, refused, error) emit a
            # synthetic single-chunk stream so clients always see SSE events.
            if result_status in ("failed", "refused") or "error" in context_result:
                yield f"data: {json.dumps({'chunk': context_result.get('error', context_result.get('answer', ''))})}\n\n"
                yield f"event: done\ndata: {json.dumps({'status': result_status, 'session_id': effective_session_id})}\n\n"
                return

            if result_status == "completed" and (context_result.get("intent") in ("small_talk",) or context_result.get("metadata", {}).get("skip_formatting")):
                answer_text = context_result.get("answer", "")
                yield f"data: {json.dumps({'chunk': answer_text})}\n\n"
                yield f"event: done\ndata: {json.dumps({'status': 'completed', 'session_id': effective_session_id})}\n\n"
                # Persist small-talk or direct translation turn
                session_ctx = context_result.get("_session_context")
                if session_ctx is not None:
                    try:
                        original_input = context_result.get("_original_input", question)
                        session_ctx.add_turn(user_input=original_input, bot_response=answer_text)
                    except Exception as e:
                        logger.warning(f"[{request_id}] Failed to persist small-talk turn: {e}")
                return

            # ── 6. Stream formatted response ──────────────────────────────────
            base_answer = context_result.get("answer", "")
            intent = context_result.get("intent", "general")
            sources = context_result.get("sources", [])
            citations = context_result.get("citations", [])
            session_ctx = context_result.get("_session_context")
            original_input = context_result.get("_original_input", question)

            from ..ai.summarizer import get_formatter_service
            formatter = get_formatter_service()

            full_response_parts = []
            try:
                async for chunk in formatter.format_response_stream(
                    base_answer=base_answer,
                    question=question,
                    intent=intent,
                    context={"sources": sources, "metadata": context_result.get("metadata", {})},
                    citations=citations,
                ):
                    # Check for client disconnect before each yield
                    if await app_request.is_disconnected():
                        logger.info(f"[{request_id}] Client disconnected mid-stream; stopping generator.")
                        return

                    full_response_parts.append(chunk)
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            except Exception as stream_err:
                logger.error(f"[{request_id}] Streaming formatter raised mid-stream: {stream_err}")
                yield f"event: error\ndata: {json.dumps({'error': 'Stream interrupted', 'session_id': effective_session_id})}\n\n"
                return

            # ── 7. Session persistence (only on full completion) ──────────────
            full_response = "".join(full_response_parts)
            if session_ctx is not None and full_response:
                try:
                    session_ctx.add_turn(user_input=original_input, bot_response=full_response)
                    logger.debug(f"[{request_id}] Session turn persisted after stream completion.")
                except Exception as e:
                    logger.warning(f"[{request_id}] Failed to persist session turn: {e}")

            # Record assistant stream response to DB
            if full_response:
                try:
                    with get_db_context() as db:
                        ChatbotDBService.sync_save_chat_message(
                            db=db,
                            session_id=effective_session_id,
                            role="assistant",
                            content=full_response
                        )
                except Exception as db_err:
                    logger.error(f"[{request_id}] Failed to log assistant stream response: {db_err}")

            # ── 8. Done event ─────────────────────────────────────────────────
            done_payload = {
                "status": context_result.get("status", "completed"),
                "session_id": effective_session_id,
                "intent": intent,
                "sources": sources,
                "message": full_response or base_answer,
                "answer": full_response or base_answer,
            }
            if context_result.get("table"):
                done_payload["table"] = context_result["table"]
            if context_result.get("visualization"):
                done_payload["visualization"] = context_result["visualization"]
            if context_result.get("suggestion"):
                done_payload["suggestion"] = context_result["suggestion"]
            if context_result.get("summary"):
                done_payload["summary"] = context_result["summary"]

            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

        finally:
            # ── Release session lock ─────────────────────────────────────────
            try:
                if redis_lock is not None:
                    await asyncio.get_event_loop().run_in_executor(None, redis_lock.release)
                elif local_lock is not None and local_lock.locked():
                    local_lock.release()
            except Exception as unlock_err:
                logger.warning(f"[{request_id}] Failed to release session lock: {unlock_err}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
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


# SESSIONS, FEEDBACK, & ATTACHMENTS CRUD ENDPOINTS

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Feedback rating from 1 to 5")
    comment: Optional[str] = Field(None, description="Optional text feedback comment")
    message_id: Optional[int] = Field(None, description="Optional reference to a specific message ID")


class AttachmentRequest(BaseModel):
    file_id: str = Field(..., description="Uploaded file ID from API Layer")
    file_name: Optional[str] = Field(None, description="Original filename")
    file_url: Optional[str] = Field(None, description="File URL path")
    message_id: Optional[int] = Field(None, description="Optional message association")


@router.get("/sessions", response_model=List[Dict[str, Any]])
def list_sessions(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    db=Depends(get_db)
):
    """List chat sessions with optional filtering for user_id and project_id."""
    query = db.query(ChatSession)
    if user_id:
        query = query.filter_by(user_id=user_id)
    if project_id:
        query = query.filter_by(project_id=project_id)
    sessions = query.order_by(ChatSession.created_at.desc()).all()
    return [
        {
            "session_id": s.session_id,
            "user_id": s.user_id,
            "project_id": s.project_id,
            "created_at": s.created_at,
            "updated_at": s.updated_at
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=Dict[str, Any])
def get_session_details(session_id: str, db=Depends(get_db)):
    """Retrieve detailed session history, context and chat messages."""
    session = db.query(ChatSession).filter_by(session_id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    messages = db.query(ChatMessage).filter_by(session_id=session_id).order_by(ChatMessage.created_at.asc()).all()
    context = session.context
    
    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "project_id": session.project_id,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "context": context.context_data if context else {},
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at
            }
            for m in messages
        ]
    }


@router.post("/sessions/{session_id}/feedback", response_model=Dict[str, Any])
def submit_feedback(session_id: str, req: FeedbackRequest, db=Depends(get_db)):
    """Submit user feedback rating and optional text comments for a session/message."""
    session = db.query(ChatSession).filter_by(session_id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    feedback = ChatbotDBService.sync_save_chat_feedback(
        db=db,
        session_id=session_id,
        rating=req.rating,
        comment=req.comment,
        message_id=req.message_id
    )
    return {"status": "success", "feedback_id": feedback.id}


@router.post("/sessions/{session_id}/attachments", response_model=Dict[str, Any])
def link_attachment(session_id: str, req: AttachmentRequest, db=Depends(get_db)):
    """Link uploaded files from the API Layer to a session or message via chat_attachments."""
    session = db.query(ChatSession).filter_by(session_id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    attachment = ChatbotDBService.sync_save_chat_attachment(
        db=db,
        session_id=session_id,
        file_id=req.file_id,
        file_name=req.file_name,
        file_url=req.file_url,
        message_id=req.message_id
    )
    return {"status": "success", "attachment_id": attachment.id}


@router.delete("/sessions/{session_id}", response_model=Dict[str, Any])
def delete_session(session_id: str, db=Depends(get_db)):
    """Delete a session. Automatically cascade deletes messages, context, feedback, attachments, etc."""
    session = db.query(ChatSession).filter_by(session_id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    db.delete(session)
    db.commit()
    return {"status": "success", "message": f"Session {session_id} and all related logs deleted successfully via cascade"}

