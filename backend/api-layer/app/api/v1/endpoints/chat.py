import json
from contextlib import asynccontextmanager
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
from app.services.main_chatbot_client import main_chatbot_client
from app.services.ownership import create_or_get_chat, owned_chat, touch_chat
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter(prefix="/chat", tags=["chat proxy"])


def upstream_payload(payload: ChatRequest, chat, user: User, request_id: str) -> dict:
    return {
        "chat_id": str(chat.id), "project_id": str(chat.project_id) if chat.project_id else None,
        "user_id": str(user.id), "role": user.role, "message": payload.message,
        "attachments": payload.attachments, "metadata": payload.metadata, "request_id": request_id,
    }


def orchestrator_query_payload(payload: ChatRequest, chat) -> dict:
    return {
        "question": payload.message,
        "session_id": str(chat.id),
    }


orchestrator_stream_payload = orchestrator_query_payload


def sse_event(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def adapt_orchestrator_sse_block(block: str, chat) -> bytes:
    if not block.strip():
        return b""
    if block.lstrip().startswith(":"):
        return f"{block}\n\n".encode()

    event = "message"
    data_lines: list[str] = []
    for line in block.split("\n"):
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if not data_lines:
        return f"{block}\n\n".encode()

    try:
        data = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        data = {"content": "\n".join(data_lines)}

    if event == "message" and isinstance(data, dict) and "chunk" in data:
        return sse_event("token", {"content": data.get("chunk", "")})

    if event == "done" and isinstance(data, dict):
        data.setdefault("chat_id", str(chat.id))
        data.setdefault("project_id", str(chat.project_id) if chat.project_id else None)
        return sse_event("done", data)

    if event == "error" and isinstance(data, dict):
        detail = data.get("detail") or data.get("error") or "Chat stream failed"
        return sse_event("error", {"detail": detail})

    if event == "clarification" and isinstance(data, dict):
        questions = data.get("questions") or []
        content = "\n".join(str(question) for question in questions) if isinstance(questions, list) else str(questions)
        return sse_event("token", {"content": content})

    return sse_event(event, data if isinstance(data, dict) else {"content": data})


@router.post("/send")
async def send_chat(payload: ChatRequest, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"chat_send:{user.id}", 30, request=request, user_id=user.id)
    chat = await create_or_get_chat(db, user.id, payload.chat_id, payload.project_id, payload.message)
    is_new = payload.chat_id is None
    if is_new:
        add_audit_log(db, "chat_created", "chat", user.id, {"chat_id": str(chat.id)})
    await touch_chat(db, chat, payload.message)
    await db.commit()
    result = await main_chatbot_client.request("POST", "/query", json=orchestrator_query_payload(payload, chat))
    if isinstance(result, dict):
        result.setdefault("chat_id", str(chat.id))
        result.setdefault("project_id", str(chat.project_id) if chat.project_id else None)
    return result


@router.post("/stream")
async def stream_chat(payload: ChatRequest, request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"chat_stream:{user.id}", 30, request=request, user_id=user.id)
    chat = await create_or_get_chat(db, user.id, payload.chat_id, payload.project_id, payload.message)
    if payload.chat_id is None:
        add_audit_log(db, "chat_created", "chat", user.id, {"chat_id": str(chat.id)})
    await touch_chat(db, chat, payload.message)
    await db.commit()
    request_id = str(uuid4())
    body = orchestrator_stream_payload(payload, chat)
    client = httpx.AsyncClient(timeout=httpx.Timeout(settings.http_timeout_seconds, read=None))
    stream_context = client.stream("POST", f"{settings.main_service_url}/query/stream", json=body, headers={"Accept": "text/event-stream"})
    try:
        upstream = await stream_context.__aenter__()
        upstream.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        await client.aclose()
        status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 503
        raise HTTPException(status_code=status_code, detail="Main Chatbot Service is temporarily unavailable") from exc

    async def events():
        buffer = ""
        try:
            yield sse_event("start", {"chat_id": str(chat.id), "project_id": str(chat.project_id) if chat.project_id else None, "request_id": request_id})
            async for chunk in upstream.aiter_bytes():
                if await request.is_disconnected():
                    break
                if chunk:
                    buffer += chunk.decode(errors="replace").replace("\r\n", "\n")
                    blocks = buffer.split("\n\n")
                    buffer = blocks.pop() or ""
                    for block in blocks:
                        adapted = adapt_orchestrator_sse_block(block, chat)
                        if adapted:
                            yield adapted
        except Exception:
            yield f"event: error\ndata: {json.dumps({'detail': 'Main Chatbot Service stream interrupted'})}\n\n".encode()
        finally:
            if buffer.strip():
                adapted = adapt_orchestrator_sse_block(buffer, chat)
                if adapted:
                    yield adapted
            await stream_context.__aexit__(None, None, None)
            await client.aclose()

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
