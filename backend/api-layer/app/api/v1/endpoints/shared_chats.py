from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import ChatShare, ChatThread
from app.schemas.common import PublicChatShareRead

router = APIRouter(prefix="/shared-chats", tags=["shared chats"])


@router.get("/{token}", response_model=PublicChatShareRead)
async def get_shared_chat(token: str, db: AsyncSession = Depends(get_db)):
    share = (
        await db.execute(
            select(ChatShare).join(ChatThread, ChatShare.chat_id == ChatThread.id).where(
                ChatShare.token == token,
                ChatShare.visibility == "public",
                ChatShare.revoked_at.is_(None),
                ChatThread.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Shared chat not found")
    return {
        "chat_id": share.chat_id,
        "token": share.token,
        "title": share.title,
        "messages": share.message_snapshot or [],
        "created_at": share.created_at,
        "updated_at": share.updated_at,
    }
