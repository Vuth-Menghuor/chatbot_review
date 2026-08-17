from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatShare, ChatThread
from app.services.audit_service import add_audit_log
from app.services.main_chatbot_client import main_chatbot_client

MAX_SHARED_MESSAGES = 200
MAX_SHARED_MESSAGE_CHARS = 20_000
MAX_SHARED_BLOCKS = 80
MAX_SHARED_SOURCES = 80

SHARED_SCALAR_FIELDS = {
    "type": str,
    "status": str,
    "responseStatus": str,
    "generationDurationMs": (int, float),
    "requestId": str,
    "chatId": str,
    "responseMode": str,
    "progressStage": str,
    "progressMessage": str,
    "streamingContent": str,
    "error": str,
    "coverage": str,
    "confidence": str,
}


def has_renderable_blocks(message: dict[str, Any]) -> bool:
    blocks = message.get("blocks")
    if not isinstance(blocks, list):
        return False
    return any(isinstance(block, dict) and isinstance(block.get("type"), str) for block in blocks)


def snapshot_has_renderable_assistant_blocks(messages: list[dict[str, Any]]) -> bool:
    return any(message.get("role") == "assistant" and has_renderable_blocks(message) for message in messages)


def serialize_share(item: ChatShare) -> dict[str, Any]:
    return {
        "chat_id": item.chat_id,
        "token": item.token,
        "visibility": item.visibility,
        "title": item.title,
        "share_url_path": f"/share/{item.token}",
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


async def get_share_by_chat(db: AsyncSession, chat_id: UUID) -> ChatShare | None:
    return (
        await db.execute(select(ChatShare).where(ChatShare.chat_id == chat_id))
    ).scalar_one_or_none()


async def new_share_token(db: AsyncSession) -> str:
    for _ in range(5):
        token = token_urlsafe(32)
        exists = (
            await db.execute(select(ChatShare.id).where(ChatShare.token == token))
        ).scalar_one_or_none()
        if not exists:
            return token
    raise HTTPException(status_code=500, detail="Could not create a unique share token")


def normalize_snapshot_messages(messages: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in messages[:MAX_SHARED_MESSAGES]:
        if not isinstance(raw, dict):
            continue
        role = raw.get("role")
        content = raw.get("content")
        if role not in {"user", "assistant", "system"} or not isinstance(content, str):
            continue
        message: dict[str, Any] = {
            "id": str(raw.get("id") or len(normalized) + 1),
            "role": role,
            "content": content[:MAX_SHARED_MESSAGE_CHARS],
        }
        for field, expected_type in SHARED_SCALAR_FIELDS.items():
            value = raw.get(field)
            if isinstance(value, expected_type):
                message[field] = value
        if isinstance(raw.get("created_at"), str):
            message["createdAt"] = raw["created_at"]
        elif isinstance(raw.get("createdAt"), str):
            message["createdAt"] = raw["createdAt"]
        if isinstance(raw.get("blocks"), list):
            message["blocks"] = raw["blocks"][:MAX_SHARED_BLOCKS]
        if isinstance(raw.get("sources"), list):
            message["sources"] = raw["sources"][:MAX_SHARED_SOURCES]
        if isinstance(raw.get("normalizedResponse"), dict):
            message["normalizedResponse"] = raw["normalizedResponse"]
        normalized.append(message)
    return normalized


async def get_orchestrator_snapshot(chat_id: UUID) -> list[dict[str, Any]]:
    try:
        result = await main_chatbot_client.request("GET", f"/sessions/{chat_id}")
    except HTTPException as exc:
        if exc.status_code in {404, 503}:
            return []
        raise
    if not isinstance(result, dict):
        return []
    messages = result.get("messages")
    return normalize_snapshot_messages(messages if isinstance(messages, list) else [])


async def create_or_update_share(
    db: AsyncSession,
    chat: ChatThread,
    user_id: UUID,
    visibility: str,
    client_snapshot: list[Any],
) -> ChatShare:
    snapshot = []
    if visibility == "public":
        client_messages = normalize_snapshot_messages(client_snapshot)
        if snapshot_has_renderable_assistant_blocks(client_messages):
            snapshot = client_messages
        else:
            snapshot = await get_orchestrator_snapshot(chat.id)
            if not snapshot:
                snapshot = client_messages

    share = await get_share_by_chat(db, chat.id)
    if share:
        share.visibility = visibility
        share.title = chat.title
        share.message_snapshot = snapshot
        share.revoked_at = None
    else:
        share = ChatShare(
            chat_id=chat.id,
            user_id=user_id,
            token=await new_share_token(db),
            visibility=visibility,
            title=chat.title,
            message_snapshot=snapshot,
        )
        db.add(share)
    add_audit_log(
        db,
        "chat_shared",
        "chat",
        user_id,
        {"chat_id": str(chat.id), "visibility": visibility},
    )
    return share


async def revoke_share(db: AsyncSession, chat: ChatThread, user_id: UUID) -> None:
    share = await get_share_by_chat(db, chat.id)
    if not share:
        return
    share.visibility = "private"
    share.message_snapshot = []
    share.revoked_at = datetime.now(timezone.utc)
    add_audit_log(
        db,
        "chat_share_revoked",
        "chat",
        user_id,
        {"chat_id": str(chat.id)},
    )
