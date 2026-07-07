from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import generate_api_key, hash_secret
from app.dependencies.auth import get_current_user
from app.models import ApiKey, User
from app.schemas.common import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from app.services.audit_service import add_audit_log

router = APIRouter(prefix="/api-keys", tags=["api keys"])


@router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(payload: ApiKeyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    raw = generate_api_key()
    item = ApiKey(user_id=user.id, key_hash=hash_secret(raw), name=payload.name)
    db.add(item)
    await db.flush()
    add_audit_log(db, "api_key_created", "api_key", user.id, {"api_key_id": str(item.id)})
    await db.commit()
    await db.refresh(item)
    return ApiKeyCreated(**ApiKeyRead.model_validate(item).model_dump(), api_key=raw)


@router.get("", response_model=list[ApiKeyRead])
async def list_api_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()))).scalars().all()


@router.delete("/{api_key_id}")
async def delete_api_key(api_key_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.user_id == user.id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="API key not found")
    item.is_active = False
    add_audit_log(db, "api_key_deleted", "api_key", user.id, {"api_key_id": str(item.id)})
    await db.commit()
    return {"message": "API key disabled"}
