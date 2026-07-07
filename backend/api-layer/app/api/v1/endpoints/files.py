from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas.file import FileDeleteResponse, FileDetailResponse, FileUpdateResponse, FileUploadResponse
from app.services.audit_service import add_audit_log
from app.services import file_service, rabbitmq_service
from app.services.file_service import PendingFileEvent

router = APIRouter(prefix="/files", tags=["files"])


async def _commit_and_publish(
    db: AsyncSession,
    user: User,
    audit_action: str,
    result,
    pending: PendingFileEvent,
):
    add_audit_log(db, audit_action, "file", user.id, {"file_id": str(result.file_id)})
    await db.commit()
    await rabbitmq_service.publish_image_event(pending.event, pending.payload)
    return result


@router.post("/upload-image", response_model=FileUploadResponse, status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result, pending = await file_service.upload_image(db, user, file)
    return await _commit_and_publish(db, user, "file_uploaded", result, pending)


@router.put("/{file_id}/update-image", response_model=FileUpdateResponse)
async def update_image(
    file_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result, pending = await file_service.update_image(db, user, file_id, file)
    return await _commit_and_publish(db, user, "file_updated", result, pending)


@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await file_service.get_file_detail(db, user, file_id)


@router.delete("/{file_id}", response_model=FileDeleteResponse)
async def delete_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result, pending = await file_service.delete_file(db, user, file_id)
    return await _commit_and_publish(db, user, "file_deleted", result, pending)
