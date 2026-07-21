from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatThread, Project


async def owned_project(db: AsyncSession, project_id: UUID, user_id: UUID, include_deleted: bool = False) -> Project:
    conditions = [Project.id == project_id, Project.user_id == user_id]
    if not include_deleted:
        conditions.append(Project.status != "deleted")
    item = (await db.execute(select(Project).where(*conditions))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Project not found")
    return item


async def owned_chat(db: AsyncSession, chat_id: UUID, user_id: UUID) -> ChatThread:
    item = (await db.execute(select(ChatThread).where(ChatThread.id == chat_id, ChatThread.user_id == user_id, ChatThread.status != "deleted"))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Chat not found")
    return item


async def create_or_get_chat(db: AsyncSession, user_id: UUID, chat_id: UUID | None, project_id: UUID | None, message: str) -> ChatThread:
    title = message.strip().replace("\n", " ")[:40] or "New Chat"
    if chat_id:
        chat = await db.get(ChatThread, chat_id)
        if chat:
            if chat.user_id != user_id or chat.status == "deleted":
                raise HTTPException(status_code=404, detail="Chat not found")
            if project_id is not None and chat.project_id != project_id:
                raise HTTPException(status_code=400, detail="project_id does not match the chat's project")
            return chat
        if project_id:
            await owned_project(db, project_id, user_id)
        chat = ChatThread(id=chat_id, user_id=user_id, project_id=project_id, title=title)
        db.add(chat)
        await db.flush()
        return chat
    if project_id:
        await owned_project(db, project_id, user_id)
    chat = ChatThread(user_id=user_id, project_id=project_id, title=title)
    db.add(chat)
    await db.flush()
    return chat


async def touch_chat(db: AsyncSession, chat: ChatThread, message: str) -> None:
    now = datetime.now(timezone.utc)
    chat.last_message_preview = message.strip()[:120]
    chat.last_activity_at = now
    if chat.project_id:
        project = await db.get(Project, chat.project_id)
        if project:
            project.last_activity_at = now
