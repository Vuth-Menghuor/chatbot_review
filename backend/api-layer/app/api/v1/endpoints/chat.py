import json
import logging
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
        try:
            yield sse_event(
                "start",
                {
                    "chat_id": str(chat.id),
                    "project_id": str(chat.project_id) if chat.project_id else None,
                    "request_id": request_id,
                    "status": "processing",
                },
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
                            yield sse_event("delta", {"content": upstream_event.content})
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
                            log_normalization_trace(data, normalized)
                            yield sse_event("done", normalized)
                            terminal_sent = True
                        elif upstream_event.type == "error" and isinstance(upstream_event.data, dict):
                            yield sse_event("error", {"detail": upstream_event.data.get("detail", "Chat stream failed")})
                            terminal_sent = True
                        elif upstream_event.type == "clarification" and isinstance(upstream_event.data, dict):
                            if not clarification_questions(upstream_event.data):
                                logger.error(
                                    "upstream_contract_inconsistency empty_clarification_questions request_id=%s chat_id=%s",
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
                                yield sse_event("done", normalized)
                                terminal_sent = True
                        if terminal_sent:
                            break
                    if not terminal_sent:
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
                result = await main_chatbot_client.request("POST", "/query", json=orchestrator_query_payload(payload, chat))
                normalized = normalize_chat_response(
                    result,
                    chat=chat,
                    include_debug=should_include_debug(user),
                    request_presentation=payload.presentation,
                ).model_dump(mode="json", exclude_none=True)
                if isinstance(result, dict):
                    log_normalization_trace(result, normalized)
                yield sse_event("done", normalized)
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
