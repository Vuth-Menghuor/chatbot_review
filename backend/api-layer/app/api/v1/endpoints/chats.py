from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import ChatThread, User
from app.schemas.common import ChatShareCreate, ChatShareRead, ChatThreadCreate, ChatThreadRead, ChatThreadUpdate
from app.services.audit_service import add_audit_log
from app.services.chat_share_service import create_or_update_share, revoke_share, serialize_share
from app.services.main_chatbot_client import main_chatbot_client
from app.services.ownership import owned_chat, owned_project

router = APIRouter(prefix="/chats", tags=["chat threads"])


@router.post("", response_model=ChatThreadRead, status_code=201)
async def create_chat(payload: ChatThreadCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if payload.project_id:
        await owned_project(db, payload.project_id, user.id)
    item = ChatThread(user_id=user.id, title=payload.title or "New Chat", project_id=payload.project_id)
    db.add(item)
    await db.flush()
    add_audit_log(db, "chat_created", "chat", user.id, {"chat_id": str(item.id)})
    await db.commit()
    await db.refresh(item)
    return item


@router.get("", response_model=list[ChatThreadRead])
async def list_chats(project_id: str | None = None, include_archived: bool = False, search: str | None = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    conditions = [ChatThread.user_id == user.id, ChatThread.status != "deleted"]
    if project_id == "null":
        conditions.append(ChatThread.project_id.is_(None))
    elif project_id:
        try:
            parsed_project_id = UUID(project_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="project_id must be a UUID or 'null'")
        await owned_project(db, parsed_project_id, user.id)
        conditions.append(ChatThread.project_id == parsed_project_id)
    if not include_archived:
        conditions.append(ChatThread.is_archived.is_(False))
    if search:
        conditions.append(or_(ChatThread.title.ilike(f"%{search}%"), ChatThread.last_message_preview.ilike(f"%{search}%")))
    query = select(ChatThread).where(*conditions).order_by(ChatThread.is_pinned.desc(), ChatThread.last_activity_at.desc().nullslast(), ChatThread.created_at.desc()).limit(limit).offset(offset)
    return (await db.execute(query)).scalars().all()


@router.get("/{chat_id}")
async def get_chat(chat_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await owned_chat(db, chat_id, user.id)
    metadata = ChatThreadRead.model_validate(item).model_dump(mode="json")
    try:
        messages = await main_chatbot_client.request("GET", f"/internal/chats/{chat_id}/messages", params={"user_id": str(user.id)})
        metadata["messages"] = messages.get("messages", messages) if isinstance(messages, dict) else messages
    except HTTPException as exc:
        if exc.status_code == 503:
            metadata["messages"] = []
            metadata["warning"] = exc.detail
        else:
            raise
    return metadata


@router.post("/{chat_id}/share", response_model=ChatShareRead)
async def share_chat(chat_id: UUID, payload: ChatShareCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat = await owned_chat(db, chat_id, user.id)
    share = await create_or_update_share(db, chat, user.id, payload.visibility, payload.client_snapshot)
    await db.commit()
    await db.refresh(share)
    return serialize_share(share)


@router.delete("/{chat_id}/share")
async def revoke_chat_share(chat_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat = await owned_chat(db, chat_id, user.id)
    await revoke_share(db, chat, user.id)
    await db.commit()
    return {"message": "Chat sharing disabled"}


@router.patch("/{chat_id}", response_model=ChatThreadRead)
async def update_chat(chat_id: UUID, payload: ChatThreadUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await owned_chat(db, chat_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    if "project_id" in changes and changes["project_id"]:
        await owned_project(db, changes["project_id"], user.id)
    for key, value in changes.items():
        setattr(item, key, value)
    if "is_archived" in changes:
        item.status = "archived" if changes["is_archived"] else "active"
    add_audit_log(db, "chat_updated", "chat", user.id, {"chat_id": str(item.id), "fields": list(changes)})
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{chat_id}")
async def delete_chat(chat_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await owned_chat(db, chat_id, user.id)
    await revoke_share(db, item, user.id)
    item.status = "deleted"
    item.is_archived = True
    add_audit_log(db, "chat_deleted", "chat", user.id, {"chat_id": str(item.id)})
    await db.commit()
    try:
        await main_chatbot_client.request("DELETE", f"/internal/chats/{chat_id}", params={"user_id": str(user.id)})
    except HTTPException:
        pass
    return {"message": "Chat deleted"}
