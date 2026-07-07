from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import ChatThread, Project, User
from app.schemas.common import ChatThreadRead, ProjectCreate, ProjectDetail, ProjectRead, ProjectUpdate
from app.services.audit_service import add_audit_log
from app.services.ownership import owned_chat, owned_project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(payload: ProjectCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = Project(user_id=user.id, **payload.model_dump())
    db.add(item)
    await db.flush()
    add_audit_log(db, "project_created", "project", user.id, {"project_id": str(item.id)})
    await db.commit()
    await db.refresh(item)
    return item


@router.get("", response_model=list[ProjectRead])
async def list_projects(include_archived: bool = False, search: str | None = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    conditions = [Project.user_id == user.id, Project.status != "deleted"]
    if not include_archived:
        conditions.extend([Project.is_archived.is_(False), Project.status == "active"])
    if search:
        conditions.append(or_(Project.name.ilike(f"%{search}%"), Project.description.ilike(f"%{search}%")))
    query = select(Project).where(*conditions).order_by(Project.is_pinned.desc(), Project.last_activity_at.desc().nullslast(), Project.created_at.desc()).limit(limit).offset(offset)
    return (await db.execute(query)).scalars().all()


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await owned_project(db, project_id, user.id)
    count = (await db.execute(select(func.count()).select_from(ChatThread).where(ChatThread.project_id == item.id, ChatThread.status != "deleted"))).scalar_one()
    recent = (await db.execute(select(ChatThread).where(ChatThread.project_id == item.id, ChatThread.status != "deleted").order_by(ChatThread.last_activity_at.desc().nullslast()).limit(5))).scalars().all()
    return ProjectDetail(**ProjectRead.model_validate(item).model_dump(), chat_count=count, recent_chats=[ChatThreadRead.model_validate(x) for x in recent])


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(project_id: UUID, payload: ProjectUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await owned_project(db, project_id, user.id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    if "is_archived" in changes:
        item.status = "archived" if changes["is_archived"] else "active"
    add_audit_log(db, "project_updated", "project", user.id, {"project_id": str(item.id), "fields": list(changes)})
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{project_id}")
async def delete_project(project_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await owned_project(db, project_id, user.id)
    item.status = "deleted"
    item.is_archived = True
    await db.execute(update(ChatThread).where(ChatThread.project_id == item.id, ChatThread.status != "deleted").values(project_id=None))
    add_audit_log(db, "project_deleted", "project", user.id, {"project_id": str(item.id)})
    await db.commit()
    return {"message": "Project deleted"}


@router.get("/{project_id}/chats", response_model=list[ChatThreadRead])
async def project_chats(project_id: UUID, include_archived: bool = False, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_project(db, project_id, user.id)
    conditions = [ChatThread.user_id == user.id, ChatThread.project_id == project_id, ChatThread.status != "deleted"]
    if not include_archived:
        conditions.append(ChatThread.is_archived.is_(False))
    return (await db.execute(select(ChatThread).where(*conditions).order_by(ChatThread.is_pinned.desc(), ChatThread.last_activity_at.desc().nullslast(), ChatThread.created_at.desc()))).scalars().all()


@router.post("/{project_id}/chats/{chat_id}", response_model=ChatThreadRead)
async def move_chat(project_id: UUID, chat_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await owned_project(db, project_id, user.id)
    chat = await owned_chat(db, chat_id, user.id)
    chat.project_id = project.id
    project.last_activity_at = datetime.now(timezone.utc)
    add_audit_log(db, "chat_moved_to_project", "chat", user.id, {"project_id": str(project.id), "chat_id": str(chat.id)})
    await db.commit()
    await db.refresh(chat)
    return chat


@router.delete("/{project_id}/chats/{chat_id}")
async def remove_chat(project_id: UUID, chat_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_project(db, project_id, user.id)
    chat = await owned_chat(db, chat_id, user.id)
    if chat.project_id != project_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Chat does not belong to this project")
    chat.project_id = None
    add_audit_log(db, "chat_removed_from_project", "chat", user.id, {"project_id": str(project_id), "chat_id": str(chat.id)})
    await db.commit()
    return {"message": "Chat removed from project"}
