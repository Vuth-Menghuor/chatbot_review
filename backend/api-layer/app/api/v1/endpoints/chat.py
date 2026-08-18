import json
import logging
import re
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
        "project_id": str(chat.project_id) if chat.project_id else None,
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


def normalized_block_types(normalized: dict) -> list[str]:
    message = normalized.get("message")
    blocks = message.get("content") if isinstance(message, dict) else []
    return [
        str(block.get("type"))
        for block in blocks or []
        if isinstance(block, dict) and block.get("type")
    ]


def normalized_suggestions(normalized: dict) -> list[str]:
    suggestions = normalized.get("suggestions")
    return [str(item) for item in suggestions or [] if str(item).strip()] if isinstance(suggestions, list) else []


def has_primary_answer_block(block: object) -> bool:
    if not isinstance(block, dict):
        return False
    block_type = str(block.get("type") or "")
    if block_type == "markdown":
        return bool(str(block.get("text") or "").strip())
    if block_type == "table":
        rows = block.get("rows")
        return isinstance(rows, list) and len(rows) > 0
    if block_type == "error":
        return bool(str(block.get("message") or "").strip())
    return block_type in {
        "summary",
        "key_value",
        "details",
        "chart",
        "prediction",
    }


def has_primary_answer(normalized: dict) -> bool:
    response = normalized.get("response")
    if isinstance(response, dict) and str(response.get("content") or "").strip():
        return True
    message = normalized.get("message")
    blocks = message.get("content") if isinstance(message, dict) else []
    return any(has_primary_answer_block(block) for block in blocks or [])


def has_any_key(data: dict, keys: set[str]) -> bool:
    return any(key in data and data.get(key) not in (None, "", [], {}) for key in keys)


def is_unreliable_trade_formatter_text(text: object) -> bool:
    if not isinstance(text, str):
        return False
    normalized = " ".join(text.upper().split())
    if not normalized:
        return False
    headings = {
        "SUMMARY OF KEY FINDINGS",
        "DATA VISUALIZATION SUGGESTIONS",
        "YEAR-OVER-YEAR OR BILATERAL COMPARISONS",
        "TRENDS AND INSIGHTS",
    }
    if any(heading in normalized or (len(normalized) >= 8 and heading.startswith(normalized)) for heading in headings):
        return True
    lowered = normalized.lower()
    return (
        "the provided trade data contains" in lowered
        or "the raw trade data provided contains" in lowered
        or "the provided trade data includes" in lowered
        or "contact the general department of customs and excise" in lowered
        or "contact gdce" in lowered
        or "detailed figures require the full dataset" in lowered
        or "requires the full dataset" in lowered
        or "require the full dataset" in lowered
    )


def has_unreliable_trade_final_text(normalized: dict) -> bool:
    response = normalized.get("response")
    if isinstance(response, dict) and is_unreliable_trade_formatter_text(response.get("content")):
        return True
    message = normalized.get("message")
    blocks = message.get("content") if isinstance(message, dict) else []
    return any(
        isinstance(block, dict)
        and block.get("type") == "markdown"
        and is_unreliable_trade_formatter_text(block.get("text"))
        for block in blocks or []
    )


def looks_like_calculator_request(question: object) -> bool:
    if not isinstance(question, str):
        return False
    text = " ".join(question.lower().replace(",", " ").split())
    if not text:
        return False
    has_calculation_verb = any(term in text for term in ("calculate", "calculator", "tax", "duty"))
    has_specific_calculator_input = any(
        term in text
        for term in (
            "cif",
            "usd",
            "declared value",
            " dv",
            "dv ",
            "acfta",
            "atiga",
            "origin",
            "china",
            "hs ",
            "hscode",
            "hs code",
        )
    ) or bool(re.search(r"\b\d{4}\.\d{2}\.\d{2}\b|\b\d{6,10}\b", text))
    return has_calculation_verb and has_specific_calculator_input


def is_generic_orchestrator_fallback_suggestions(normalized: dict) -> bool:
    generic = {
        "how do i classify my goods?",
        "how is customs duty calculated?",
        "what documents do i need to import?",
    }
    values = {item.strip().lower() for item in normalized_suggestions(normalized)}
    if generic.issubset(values):
        return True
    message = normalized.get("message")
    blocks = message.get("content") if isinstance(message, dict) else []
    for block in blocks or []:
        if not isinstance(block, dict) or block.get("type") != "suggestions":
            continue
        items = block.get("items")
        block_values = {str(item).strip().lower() for item in items or [] if str(item).strip()} if isinstance(items, list) else set()
        if generic.issubset(block_values):
            return True
    return False


def has_meaningful_calculator_structured_content(raw_stream_done: dict, normalized: dict) -> bool:
    calculator_raw_keys = {"calculator_result", "structured_result", "product", "inputs", "tax_breakdown", "phases"}
    if has_any_key(raw_stream_done, calculator_raw_keys):
        return True
    block_types = set(normalized_block_types(normalized))
    if "summary" not in block_types:
        return False
    return bool(block_types.intersection({"key_value", "details", "table"}))


def stream_final_fallback_reason(
    raw_stream_done: dict,
    normalized: dict,
    *,
    question: str | None = None,
) -> str | None:
    status = str(normalized.get("status") or "").lower()
    if status in {"failed", "clarification_required"}:
        return None
    service = str(normalized.get("service") or raw_stream_done.get("service") or "").lower()
    intent = str(normalized.get("intent") or raw_stream_done.get("intent") or "").lower()
    block_types = set(normalized_block_types(normalized))
    expected_calculator = (
        service == "calculator"
        or "calc" in intent
        or looks_like_calculator_request(question)
    )

    if expected_calculator:
        if service in {"general", "unknown", ""} or intent in {"general", "small_talk", "smalltalk", ""}:
            return "calculator_stream_done_unexpected_general_result"
        if is_generic_orchestrator_fallback_suggestions(normalized):
            return "calculator_stream_done_generic_fallback_suggestions"
        if not has_primary_answer(normalized):
            return "calculator_stream_done_missing_primary_answer"
        if not has_meaningful_calculator_structured_content(raw_stream_done, normalized):
            return "calculator_stream_done_missing_structured_payload"
        return None

    if service == "general" or intent in {"general", "small_talk", "smalltalk"}:
        if not has_primary_answer(normalized):
            return "general_stream_done_missing_primary_answer"
        return None

    if status == "completed" and not has_primary_answer(normalized):
        return "stream_done_missing_primary_answer"

    if service == "trade" or intent.startswith("trade"):
        if has_unreliable_trade_final_text(normalized):
            return "trade_stream_done_generic_formatter_text"
        trade_raw_keys = {"table", "chart", "charts", "data", "rows", "series"}
        if has_any_key(raw_stream_done, trade_raw_keys):
            return None
        if block_types.intersection({"table", "chart", "summary"}):
            return None
        return "trade_stream_done_missing_structured_payload"

    return None


def needs_authoritative_query_fallback(raw_stream_done: dict, normalized: dict) -> bool:
    return stream_final_fallback_reason(raw_stream_done, normalized) is not None


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


def log_stream_final_decision(
    *,
    request_id: str,
    chat,
    question: str,
    stream_start_service: str | None,
    stream_start_intent: str | None,
    stream_done: dict | None,
    stream_normalized: dict | None,
    fallback_used: bool,
    fallback_reason: str | None,
    authoritative: dict,
) -> None:
    logger.info(
        "stream_final_decision %s",
        json.dumps(
            {
                "request_id": request_id,
                "chat_id": str(chat.id),
                "question": question,
                "stream_start_service": stream_start_service,
                "stream_start_intent": stream_start_intent,
                "stream_done_service": (stream_normalized or {}).get("service") or (stream_done or {}).get("service"),
                "stream_done_intent": (stream_normalized or {}).get("intent") or (stream_done or {}).get("intent"),
                "stream_done_block_types": normalized_block_types(stream_normalized or {}),
                "authoritative_fallback_used": fallback_used,
                "authoritative_fallback_reason": fallback_reason,
                "authoritative_service": authoritative.get("service"),
                "authoritative_intent": authoritative.get("intent"),
                "authoritative_block_types": normalized_block_types(authoritative),
            },
            ensure_ascii=False,
        ),
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


def normalize_final_response(raw: dict, *, chat, user: User, request_presentation: dict | None) -> dict:
    return normalize_chat_response(
        raw,
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
    normalized = normalize_final_response(
        result,
        chat=chat,
        user=user,
        request_presentation=payload.presentation,
    )
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

    async def query_fallback_response() -> dict:
        result = await main_chatbot_client.request("POST", "/query", json=orchestrator_query_payload(payload, chat))
        normalized = normalize_final_response(
            result,
            chat=chat,
            user=user,
            request_presentation=payload.presentation,
        )
        if isinstance(result, dict):
            log_normalization_trace(result, normalized)
        return normalized

    async def events():
        # The public SSE contract deliberately contains only start, delta, done,
        # and error. Structured response blocks belong exclusively in `done`.
        yield sse_event("start", {
            "chat_id": str(chat.id), "project_id": str(chat.project_id) if chat.project_id else None,
            "request_id": request_id, "status": "processing",
        })
        if await request.is_disconnected():
            return
        try:
            if settings.use_standard_chat_stream:
                yield sse_event("done", await query_fallback_response())
                return

            upstream_events = main_chatbot_client.stream_chat(body)
            try:
                stream_start_service: str | None = None
                stream_start_intent: str | None = None
                try:
                    async for upstream_event in upstream_events:
                        if await request.is_disconnected():
                            return
                        if upstream_event.type == "delta" and upstream_event.content:
                            yield sse_event("delta", {"content": upstream_event.content})
                        elif upstream_event.type == "progress" and isinstance(upstream_event.data, dict):
                            stream_start_service = stream_start_service or (
                                str(upstream_event.data.get("service")) if upstream_event.data.get("service") else None
                            )
                            stream_start_intent = stream_start_intent or (
                                str(upstream_event.data.get("intent")) if upstream_event.data.get("intent") else None
                            )
                        elif upstream_event.type == "done" and isinstance(upstream_event.data, dict):
                            data = upstream_event.data
                            data.setdefault("chat_id", str(chat.id))
                            data.setdefault("project_id", str(chat.project_id) if chat.project_id else None)
                            normalized = normalize_final_response(
                                data,
                                chat=chat,
                                user=user,
                                request_presentation=payload.presentation,
                            )
                            fallback_reason = stream_final_fallback_reason(data, normalized, question=payload.message)
                            if fallback_reason:
                                authoritative = await query_fallback_response()
                                log_stream_final_decision(
                                    request_id=request_id,
                                    chat=chat,
                                    question=payload.message,
                                    stream_start_service=stream_start_service,
                                    stream_start_intent=stream_start_intent,
                                    stream_done=data,
                                    stream_normalized=normalized,
                                    fallback_used=True,
                                    fallback_reason=fallback_reason,
                                    authoritative=authoritative,
                                )
                                normalized = authoritative
                            else:
                                log_stream_final_decision(
                                    request_id=request_id,
                                    chat=chat,
                                    question=payload.message,
                                    stream_start_service=stream_start_service,
                                    stream_start_intent=stream_start_intent,
                                    stream_done=data,
                                    stream_normalized=normalized,
                                    fallback_used=False,
                                    fallback_reason=None,
                                    authoritative=normalized,
                                )
                            log_normalization_trace(data, normalized)
                            yield sse_event("done", normalized)
                            return
                        elif upstream_event.type == "clarification" and isinstance(upstream_event.data, dict):
                            if clarification_questions(upstream_event.data):
                                yield sse_event("done", normalized_clarification_payload(
                                    upstream_event.data, chat=chat, user=user, request_presentation=payload.presentation,
                                ))
                                return
                            break
                        elif upstream_event.type == "error":
                            break
                except Exception:
                    # The final /query response is safe to use when the live
                    # connection breaks after a partial delta.
                    logger.warning("main_chatbot_stream_interrupted request_id=%s chat_id=%s", request_id, chat.id)
            finally:
                aclose = getattr(upstream_events, "aclose", None)
                if aclose:
                    with suppress(Exception):
                        await aclose()

            # A stream that cannot provide a terminal response falls back to
            # /query, but never fabricates token or structured-block events.
            if not await request.is_disconnected():
                yield sse_event("done", await query_fallback_response())
        except httpx.HTTPStatusError as exc:
            if is_stream_endpoint_unavailable(exc):
                try:
                    yield sse_event("done", await query_fallback_response())
                except Exception:
                    yield sse_event("error", {"detail": "Main Chatbot Service is temporarily unavailable"})
            else:
                yield sse_event("error", {"detail": "Main Chatbot Service is temporarily unavailable"})
        except httpx.RequestError:
            yield sse_event("error", {"detail": "Main Chatbot Service is temporarily unavailable"})
        except Exception:
            logger.exception("main_chatbot_stream_exception request_id=%s chat_id=%s", request_id, chat.id)
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
