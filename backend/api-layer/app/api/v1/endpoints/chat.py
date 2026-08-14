import json
import logging
import asyncio
from contextlib import suppress
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas.common import ChatRequest, FeedbackRequest
from app.services.audit_service import add_audit_log
from app.services.chat_debug import can_include_chat_response_debug
from app.services.chat_response_normalizer import normalize_chat_response
from app.services.main_chatbot_client import main_chatbot_client
from app.services.ownership import create_or_get_chat, owned_chat, touch_chat
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter(prefix="/chat", tags=["chat proxy"])
logger = logging.getLogger(__name__)


def upstream_payload(payload: ChatRequest, chat, user: User, request_id: str) -> dict:
    return {
        "chat_id": str(chat.id), "project_id": str(chat.project_id) if chat.project_id else None,
        "user_id": str(user.id), "role": user.role, "message": payload.message,
        "attachments": payload.attachments, "metadata": payload.metadata, "request_id": request_id,
    }


def orchestrator_query_payload(payload: ChatRequest, chat) -> dict:
    body = {
        "question": payload.message,
        "session_id": str(chat.id),
        "chat_id": str(chat.id),
    }
    if payload.presentation:
        body["presentation"] = payload.presentation
    if payload.context:
        body["context"] = payload.context
    return body


def orchestrator_stream_payload(payload: ChatRequest, chat, request_id: str) -> dict:
    body = {
        "question": payload.message,
        "session_id": str(chat.id),
        "chat_id": str(chat.id),
        "project_id": str(chat.project_id) if chat.project_id else None,
        "request_id": request_id,
    }
    if payload.presentation:
        body["presentation"] = payload.presentation
    if payload.context:
        body["context"] = payload.context
    return body


def sse_event(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def stream_progress_event(
    *,
    status: str = "processing",
    mode: str = "stream",
    stage: str,
    message: str,
    **extra,
) -> bytes:
    payload = {
        "status": status,
        "mode": mode,
        "stage": stage,
        "message": message,
        **extra,
    }
    return sse_event("progress", payload)


def fallback_stream_text(normalized: dict) -> str:
    response = normalized.get("response")
    if isinstance(response, dict):
        content = response.get("content")
        if isinstance(content, str) and content.strip():
            return content

    message = normalized.get("message")
    if isinstance(message, dict):
        parts: list[str] = []
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "markdown":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        if parts:
            return "\n\n".join(parts)
    return ""


def fallback_delta_chunks(text: str, *, max_words: int = 3) -> list[str]:
    words = text.split(" ")
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if len(current) >= max_words or word.endswith((".", "?", "!", ":", ";")):
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    return [f"{chunk} " for chunk in chunks if chunk.strip()]


def normalized_message_blocks(normalized: dict) -> list[dict]:
    message = normalized.get("message")
    if not isinstance(message, dict):
        return []
    blocks = message.get("content")
    if not isinstance(blocks, list):
        return []
    return [block for block in blocks if isinstance(block, dict) and block.get("type")]


def should_stream_normalized_blocks(normalized: dict) -> bool:
    blocks = normalized_message_blocks(normalized)
    if not blocks:
        return False
    service = str(normalized.get("service") or "").lower()
    if service in {"calculator", "retrieval", "trade"}:
        return True
    return len(blocks) > 1 or any(block.get("type") != "markdown" for block in blocks)


def has_calculator_structured_blocks(normalized: dict) -> bool:
    structural_types = {"summary", "key_value", "table", "details"}
    return any(block.get("type") in structural_types for block in normalized_message_blocks(normalized))


def needs_calculator_query_fallback(normalized: dict) -> bool:
    return (
        str(normalized.get("service") or "").lower() == "calculator"
        and str(normalized.get("status") or "").lower() != "failed"
        and not has_calculator_structured_blocks(normalized)
    )


async def fallback_delta_events(normalized: dict, request: Request):
    text = fallback_stream_text(normalized)
    for chunk in fallback_delta_chunks(text):
        if await request.is_disconnected():
            return
        yield sse_event("delta", {"content": chunk})
        await asyncio.sleep(0.055)


async def normalized_stream_events(normalized: dict, request: Request):
    if should_stream_normalized_blocks(normalized):
        for index, block in enumerate(normalized_message_blocks(normalized)):
            if await request.is_disconnected():
                return
            block_payload = dict(block)
            block_payload.setdefault("stream_index", index)
            yield sse_event("block", block_payload)
            await asyncio.sleep(0.035)
        return

    async for event in fallback_delta_events(normalized, request):
        yield event


def should_include_debug(user: User) -> bool:
    return can_include_chat_response_debug(
        enable_debug=settings.enable_chat_response_debug,
        environment=settings.environment,
        role=getattr(user, "role", ""),
    )


def log_normalization_trace(orchestrator_response: dict, normalized_response: dict) -> None:
    if settings.environment.lower() not in {"development", "local", "dev"}:
        return
    orchestrator_answer = orchestrator_response.get("answer")
    backend_response_content = (normalized_response.get("response") or {}).get("content")
    trace = {
        "orchestrator_request_id": orchestrator_response.get("request_id"),
        "orchestrator_session_id": orchestrator_response.get("session_id"),
        "orchestrator_answer": orchestrator_answer,
        "backend_response_content": backend_response_content,
    }
    logger.info("normalization_trace %s", json.dumps(trace, ensure_ascii=False))
    if isinstance(orchestrator_answer, str) and backend_response_content != orchestrator_answer:
        logger.error(
            "normalization_changed_orchestrator_answer %s",
            json.dumps(trace, ensure_ascii=False),
        )


def is_normalized_v1_response(data: dict) -> bool:
    return (
        data.get("api_version") == "1.0"
        and isinstance(data.get("response"), dict)
        and isinstance(data.get("message"), dict)
        and isinstance(data["message"].get("content"), list)
    )


def is_stream_endpoint_unavailable(exc: httpx.HTTPStatusError) -> bool:
    return exc.response.status_code in {404, 405, 501}


def clarification_questions(data: dict) -> list[str]:
    questions = data.get("questions")
    if not isinstance(questions, list):
        return []
    return [str(question).strip() for question in questions if str(question).strip()]


def normalized_clarification_payload(data: dict, *, chat, user: User, request_presentation: dict | None) -> dict:
    questions = clarification_questions(data)
    payload = dict(data)
    payload["status"] = "clarification_required"
    payload["clarifications"] = questions
    payload.setdefault("answer", data.get("message") or "More information is required to complete the request.")
    payload.setdefault("intent", "general")
    payload.setdefault("session_id", str(chat.id))
    return normalize_chat_response(
        payload,
        chat=chat,
        include_debug=should_include_debug(user),
        request_presentation=request_presentation,
    ).model_dump(mode="json", exclude_none=True)


@router.post("/send")
async def send_chat(payload: ChatRequest, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"chat_send:{user.id}", 30, request=request, user_id=user.id)
    chat = await create_or_get_chat(db, user.id, payload.chat_id, payload.project_id, payload.message)
    is_new = payload.chat_id is None
    if is_new:
        add_audit_log(db, "chat_created", "chat", user.id, {"chat_id": str(chat.id)})
    await touch_chat(db, chat, payload.message)
    await db.commit()
    body = orchestrator_query_payload(payload, chat)
    result = await main_chatbot_client.request("POST", "/query", json=body)
    include_debug = should_include_debug(user)
    normalized = normalize_chat_response(
        result,
        chat=chat,
        include_debug=include_debug,
        request_presentation=payload.presentation,
    ).model_dump(mode="json", exclude_none=True)
    if isinstance(result, dict):
        log_normalization_trace(result, normalized)
    return normalized


@router.post("/stream")
async def stream_chat(payload: ChatRequest, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"chat_stream:{user.id}", 30, request=request, user_id=user.id)
    chat = await create_or_get_chat(db, user.id, payload.chat_id, payload.project_id, payload.message)
    if payload.chat_id is None:
        add_audit_log(db, "chat_created", "chat", user.id, {"chat_id": str(chat.id)})
    await touch_chat(db, chat, payload.message)
    await db.commit()
    request_id = str(uuid4())
    body = orchestrator_stream_payload(payload, chat, request_id)

    async def events():
        if settings.use_standard_chat_stream:
            # Obtain the final response through the exact same route and
            # normalizer used by /chat/send.  SSE remains the presentation
            # transport: the frontend progressively renders these blocks, but
            # the terminal `done` payload has the standard v1 response shape.
            try:
                yield sse_event(
                    "start",
                    {
                        "chat_id": str(chat.id),
                        "project_id": str(chat.project_id) if chat.project_id else None,
                        "request_id": request_id,
                        "status": "processing",
                        "mode": "stream",
                    },
                )
                yield stream_progress_event(
                    request_id=request_id,
                    chat_id=str(chat.id),
                    project_id=str(chat.project_id) if chat.project_id else None,
                    mode="sync",
                    stage="processing",
                    message="Preparing response...",
                )
                if await request.is_disconnected():
                    return

                result = await main_chatbot_client.request(
                    "POST",
                    "/query",
                    json=orchestrator_query_payload(payload, chat),
                )
                normalized = normalize_chat_response(
                    result,
                    chat=chat,
                    include_debug=should_include_debug(user),
                    request_presentation=payload.presentation,
                ).model_dump(mode="json", exclude_none=True)
                if isinstance(result, dict):
                    log_normalization_trace(result, normalized)

                yield stream_progress_event(
                    request_id=request_id,
                    chat_id=str(chat.id),
                    project_id=str(chat.project_id) if chat.project_id else None,
                    status=str(normalized.get("status") or "completed"),
                    mode="sync",
                    stage="rendering",
                    message="Rendering response...",
                )
                yield sse_event("done", normalized)
            except HTTPException as exc:
                yield sse_event("error", {"detail": str(exc.detail)})
            except httpx.RequestError:
                yield sse_event("error", {"detail": "Main Chatbot Service is temporarily unavailable"})
            except Exception:
                logger.exception(
                    "standard_chat_stream_exception request_id=%s chat_id=%s",
                    request_id,
                    chat.id,
                )
                yield sse_event("error", {"detail": "Main Chatbot Service stream interrupted"})
            return

        async def query_fallback_response() -> dict:
            result = await main_chatbot_client.request(
                "POST",
                "/query",
                json=orchestrator_query_payload(payload, chat),
            )
            normalized = normalize_chat_response(
                result,
                chat=chat,
                include_debug=should_include_debug(user),
                request_presentation=payload.presentation,
            ).model_dump(mode="json", exclude_none=True)
            if isinstance(result, dict):
                log_normalization_trace(result, normalized)
            return normalized

        try:
            yield sse_event(
                "start",
                {
                    "chat_id": str(chat.id),
                    "project_id": str(chat.project_id) if chat.project_id else None,
                    "request_id": request_id,
                    "status": "processing",
                    "mode": "stream",
                },
            )
            yield stream_progress_event(
                request_id=request_id,
                chat_id=str(chat.id),
                project_id=str(chat.project_id) if chat.project_id else None,
                stage="queued",
                message="Starting response stream...",
            )
            if await request.is_disconnected():
                return

            try:
                upstream_events = main_chatbot_client.stream_chat(body)
                terminal_sent = False
                try:
                    while True:
                        if await request.is_disconnected():
                            return
                        try:
                            upstream_event = await anext(upstream_events)
                        except StopAsyncIteration:
                            break
                        if upstream_event.type == "delta" and upstream_event.content:
                            # Forward upstream text immediately. Holding these chunks until
                            # `done` makes a nominal SSE response appear non-streaming in the UI.
                            yield sse_event("delta", {"content": upstream_event.content})
                        elif upstream_event.type == "progress" and isinstance(upstream_event.data, dict):
                            data = upstream_event.data
                            stage = str(data.get("stage") or "processing")
                            message = str(data.get("message") or "Processing request...")
                            yield stream_progress_event(
                                request_id=request_id,
                                chat_id=str(chat.id),
                                project_id=str(chat.project_id) if chat.project_id else None,
                                status=str(data.get("status") or "processing"),
                                mode=str(data.get("mode") or "stream"),
                                stage=stage,
                                message=message,
                            )
                        elif upstream_event.type == "done" and isinstance(upstream_event.data, dict):
                            data = upstream_event.data
                            data.setdefault("chat_id", str(chat.id))
                            data.setdefault("project_id", str(chat.project_id) if chat.project_id else None)
                            if is_normalized_v1_response(data):
                                normalized = data
                            else:
                                normalized = normalize_chat_response(
                                    data,
                                    chat=chat,
                                    include_debug=should_include_debug(user),
                                    request_presentation=payload.presentation,
                                ).model_dump(mode="json", exclude_none=True)
                            if needs_calculator_query_fallback(normalized):
                                logger.warning(
                                    "calculator_stream_missing_structured_blocks request_id=%s chat_id=%s",
                                    request_id,
                                    chat.id,
                                )
                                normalized = await query_fallback_response()
                            log_normalization_trace(data, normalized)
                            yield stream_progress_event(
                                request_id=request_id,
                                chat_id=str(chat.id),
                                project_id=str(chat.project_id) if chat.project_id else None,
                                status=str(normalized.get("status") or "completed"),
                                mode="stream",
                                stage="finalizing",
                                message="Finalizing response...",
                            )
                            if should_stream_normalized_blocks(normalized):
                                async for event in normalized_stream_events(normalized, request):
                                    yield event
                            yield sse_event("done", normalized)
                            terminal_sent = True
                        elif upstream_event.type == "error" and isinstance(upstream_event.data, dict):
                            detail = str(upstream_event.data.get("detail") or "Chat stream failed")
                            logger.warning(
                                "main_chatbot_stream_error_event request_id=%s chat_id=%s detail=%s",
                                request_id,
                                chat.id,
                                detail,
                            )
                            if await request.is_disconnected():
                                return
                            yield stream_progress_event(
                                request_id=request_id,
                                chat_id=str(chat.id),
                                project_id=str(chat.project_id) if chat.project_id else None,
                                status="processing",
                                mode="sync",
                                stage="fallback",
                                message="Completing response without streaming...",
                            )
                            try:
                                normalized = await query_fallback_response()
                                async for event in normalized_stream_events(normalized, request):
                                    yield event
                                yield stream_progress_event(
                                    request_id=request_id,
                                    chat_id=str(chat.id),
                                    project_id=str(chat.project_id) if chat.project_id else None,
                                    status=str(normalized.get("status") or "completed"),
                                    mode="sync",
                                    stage="finalizing",
                                    message="Finalizing response...",
                                )
                                yield sse_event("done", normalized)
                            except Exception:
                                logger.exception(
                                    "main_chatbot_stream_error_event_fallback_failed request_id=%s chat_id=%s",
                                    request_id,
                                    chat.id,
                                )
                                yield sse_event("error", {"detail": detail})
                            terminal_sent = True
                        elif upstream_event.type == "clarification" and isinstance(upstream_event.data, dict):
                            if not clarification_questions(upstream_event.data):
                                logger.error(
                                    "upstream_contract_inconsistency empty_clarification_questions request_id=%s chat_id=%s",
                                    request_id,
                                    chat.id,
                                )
                                if await request.is_disconnected():
                                    return
                                yield stream_progress_event(
                                    request_id=request_id,
                                    chat_id=str(chat.id),
                                    project_id=str(chat.project_id) if chat.project_id else None,
                                    status="processing",
                                    mode="sync",
                                    stage="fallback",
                                    message="Completing response without streaming...",
                                )
                                try:
                                    normalized = await query_fallback_response()
                                    async for event in normalized_stream_events(normalized, request):
                                        yield event
                                    yield stream_progress_event(
                                        request_id=request_id,
                                        chat_id=str(chat.id),
                                        project_id=str(chat.project_id) if chat.project_id else None,
                                        status=str(normalized.get("status") or "completed"),
                                        mode="sync",
                                        stage="finalizing",
                                        message="Finalizing response...",
                                    )
                                    yield sse_event("done", normalized)
                                except Exception:
                                    logger.exception(
                                        "empty_clarification_questions_fallback_failed request_id=%s chat_id=%s",
                                        request_id,
                                        chat.id,
                                    )
                                    yield sse_event("error", {"detail": "Main Chatbot Service stream interrupted"})
                                terminal_sent = True
                            else:
                                normalized = normalized_clarification_payload(
                                    upstream_event.data,
                                    chat=chat,
                                    user=user,
                                    request_presentation=payload.presentation,
                                )
                                async for event in normalized_stream_events(normalized, request):
                                    yield event
                                yield sse_event("done", normalized)
                                terminal_sent = True
                        if terminal_sent:
                            break
                    if not terminal_sent:
                        logger.warning(
                            "main_chatbot_stream_missing_terminal request_id=%s chat_id=%s",
                            request_id,
                            chat.id,
                        )
                        if await request.is_disconnected():
                            return
                        yield stream_progress_event(
                            request_id=request_id,
                            chat_id=str(chat.id),
                            project_id=str(chat.project_id) if chat.project_id else None,
                            status="processing",
                            mode="sync",
                            stage="fallback",
                            message="Completing response without streaming...",
                        )
                        try:
                            normalized = await query_fallback_response()
                            async for event in normalized_stream_events(normalized, request):
                                yield event
                            yield stream_progress_event(
                                request_id=request_id,
                                chat_id=str(chat.id),
                                project_id=str(chat.project_id) if chat.project_id else None,
                                status=str(normalized.get("status") or "completed"),
                                mode="sync",
                                stage="finalizing",
                                message="Finalizing response...",
                            )
                            yield sse_event("done", normalized)
                        except Exception:
                            logger.exception(
                                "main_chatbot_stream_missing_terminal_fallback_failed request_id=%s chat_id=%s",
                                request_id,
                                chat.id,
                            )
                            yield sse_event("error", {"detail": "Main Chatbot Service stream interrupted"})
                finally:
                    aclose = getattr(upstream_events, "aclose", None)
                    if aclose:
                        with suppress(Exception):
                            await aclose()
            except httpx.HTTPStatusError as exc:
                if not is_stream_endpoint_unavailable(exc):
                    raise
                if await request.is_disconnected():
                    return
                normalized = await query_fallback_response()
                async for event in normalized_stream_events(normalized, request):
                    yield event
                yield stream_progress_event(
                    request_id=request_id,
                    chat_id=str(chat.id),
                    project_id=str(chat.project_id) if chat.project_id else None,
                    status="completed",
                    mode="sync",
                    stage="finalizing",
                    message="Finalizing response...",
                )
                yield sse_event("done", normalized)
            except httpx.RequestError:
                raise
            except Exception:
                logger.exception(
                    "main_chatbot_stream_exception request_id=%s chat_id=%s",
                    request_id,
                    chat.id,
                )
                if await request.is_disconnected():
                    return
                yield stream_progress_event(
                    request_id=request_id,
                    chat_id=str(chat.id),
                    project_id=str(chat.project_id) if chat.project_id else None,
                    status="processing",
                    mode="sync",
                    stage="fallback",
                    message="Completing response without streaming...",
                )
                try:
                    normalized = await query_fallback_response()
                    async for event in normalized_stream_events(normalized, request):
                        yield event
                    yield stream_progress_event(
                        request_id=request_id,
                        chat_id=str(chat.id),
                        project_id=str(chat.project_id) if chat.project_id else None,
                        status=str(normalized.get("status") or "completed"),
                        mode="sync",
                        stage="finalizing",
                        message="Finalizing response...",
                    )
                    yield sse_event("done", normalized)
                except Exception:
                    logger.exception(
                        "main_chatbot_stream_exception_fallback_failed request_id=%s chat_id=%s",
                        request_id,
                        chat.id,
                    )
                    yield sse_event("error", {"detail": "Main Chatbot Service stream interrupted"})
        except httpx.HTTPStatusError as exc:
            detail = "Main Chatbot Service is temporarily unavailable"
            yield sse_event("error", {"detail": detail, "status_code": exc.response.status_code})
        except httpx.RequestError:
            yield sse_event("error", {"detail": "Main Chatbot Service is temporarily unavailable"})
        except Exception:
            yield sse_event("error", {"detail": "Main Chatbot Service stream interrupted"})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@router.get("/history")
async def history(chat_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from uuid import UUID
    try:
        parsed = UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid chat_id")
    await owned_chat(db, parsed, user.id)
    return {
        "chat_id": chat_id,
        "messages": [],
        "warning": "The orchestrator service does not expose a chat history endpoint; thread metadata is stored by the API layer.",
    }


@router.post("/feedback")
async def feedback(payload: FeedbackRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_chat(db, payload.chat_id, user.id)
    add_audit_log(
        db,
        "chat_feedback",
        "chat",
        user.id,
        {
            "chat_id": str(payload.chat_id),
            "message_id": payload.message_id,
            "rating": payload.rating,
            "comment": payload.comment,
        },
    )
    await db.commit()
    return {"message": "Feedback recorded"}
