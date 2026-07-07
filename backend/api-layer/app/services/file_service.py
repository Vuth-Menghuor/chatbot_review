import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import FileJob, FileRecord, User
from app.schemas.file import FileDeleteResponse, FileDetailResponse, FileUpdateResponse, FileUploadResponse
from app.services import minio_service

logger = logging.getLogger(__name__)

ALLOWED_EXTENSION_TO_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


@dataclass
class PendingFileEvent:
    event: str
    payload: dict[str, Any]


def _normalize_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def _extension_from_filename(filename: str | None) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lower()


def validate_image_file(content_type: str | None, size_bytes: int, filename: str | None) -> str:
    normalized_type = _normalize_content_type(content_type)
    extension = _extension_from_filename(filename)

    if extension not in {f".{ext}" for ext in settings.allowed_image_extensions}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image file extension")

    allowed_types = {item.lower() for item in settings.allowed_image_types}
    expected_type = ALLOWED_EXTENSION_TO_CONTENT_TYPE.get(extension)
    if normalized_type not in allowed_types:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image content type")
    if expected_type and normalized_type not in {expected_type, "image/jpg"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File extension does not match content type")

    if size_bytes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file is not allowed")
    if size_bytes > settings.max_image_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds maximum size of {settings.max_image_size_mb} MB",
        )

    return expected_type or normalized_type


def generate_object_key(user_id: UUID, extension: str) -> str:
    ext = extension.lstrip(".")
    return f"users/{user_id}/{uuid4()}.{ext}"


async def _read_upload(upload: UploadFile) -> tuple[bytes, str]:
    content = await upload.read()
    content_type = validate_image_file(upload.content_type, len(content), upload.filename)
    return content, content_type


async def owned_file(db: AsyncSession, file_id: UUID, user: User, include_deleted: bool = False) -> FileRecord:
    item = (await db.execute(select(FileRecord).where(FileRecord.id == file_id))).scalar_one_or_none()
    if not item or (item.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if item.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this file")
    return item


async def upload_image(db: AsyncSession, user: User, upload: UploadFile) -> tuple[FileUploadResponse, PendingFileEvent]:
    content, content_type = await _read_upload(upload)
    extension = _extension_from_filename(upload.filename).lstrip(".")
    object_key = generate_object_key(user.id, extension)

    await asyncio.to_thread(minio_service.upload_file, object_key, content, content_type)
    public_url = minio_service.build_public_url(object_key)

    file_record = FileRecord(
        user_id=user.id,
        bucket_name=settings.minio_bucket,
        object_key=object_key,
        original_name=upload.filename or f"upload.{extension}",
        content_type=content_type,
        size_bytes=len(content),
        file_type="image",
        status="pending",
        public_url=public_url,
    )
    db.add(file_record)
    await db.flush()
    job = FileJob(
        file_id=file_record.id,
        job_type="image.uploaded",
        status="pending",
        payload_json={
            "file_id": str(file_record.id),
            "user_id": str(file_record.user_id),
            "bucket_name": file_record.bucket_name,
            "object_key": file_record.object_key,
            "content_type": file_record.content_type,
        },
    )
    db.add(job)
    await db.flush()
    await db.refresh(file_record)

    payload = {**job.payload_json, "job_id": str(job.id)}
    response = FileUploadResponse(
        file_id=file_record.id,
        object_key=file_record.object_key,
        bucket=file_record.bucket_name,
        status=file_record.status,
        url=file_record.public_url,
    )
    return response, PendingFileEvent("image.uploaded", payload)


async def update_image(
    db: AsyncSession, user: User, file_id: UUID, upload: UploadFile
) -> tuple[FileUpdateResponse, PendingFileEvent]:
    file_record = await owned_file(db, file_id, user)
    content, content_type = await _read_upload(upload)
    extension = _extension_from_filename(upload.filename).lstrip(".")
    old_object_key = file_record.object_key
    new_object_key = generate_object_key(user.id, extension)

    await asyncio.to_thread(minio_service.upload_file, new_object_key, content, content_type)
    public_url = minio_service.build_public_url(new_object_key)

    file_record.object_key = new_object_key
    file_record.original_name = upload.filename or file_record.original_name
    file_record.content_type = content_type
    file_record.size_bytes = len(content)
    file_record.status = "pending"
    file_record.public_url = public_url
    await db.flush()

    job = FileJob(
        file_id=file_record.id,
        job_type="image.updated",
        status="pending",
        payload_json={
            "file_id": str(file_record.id),
            "user_id": str(file_record.user_id),
            "bucket_name": file_record.bucket_name,
            "object_key": file_record.object_key,
            "content_type": file_record.content_type,
            "old_object_key": old_object_key,
        },
    )
    db.add(job)
    await db.flush()

    payload = {**job.payload_json, "job_id": str(job.id)}
    await asyncio.to_thread(minio_service.delete_file, old_object_key)

    response = FileUpdateResponse(
        file_id=file_record.id,
        object_key=file_record.object_key,
        bucket=file_record.bucket_name,
        status=file_record.status,
        url=file_record.public_url,
    )
    return response, PendingFileEvent("image.updated", payload)


async def get_file_detail(db: AsyncSession, user: User, file_id: UUID) -> FileDetailResponse:
    file_record = await owned_file(db, file_id, user)
    return FileDetailResponse.model_validate(file_record)


async def delete_file(db: AsyncSession, user: User, file_id: UUID) -> tuple[FileDeleteResponse, PendingFileEvent]:
    file_record = await owned_file(db, file_id, user)
    file_record.status = "deleted"
    file_record.deleted_at = datetime.now(timezone.utc)
    await db.flush()

    job = FileJob(
        file_id=file_record.id,
        job_type="image.deleted",
        status="pending",
        payload_json={
            "file_id": str(file_record.id),
            "user_id": str(file_record.user_id),
            "bucket_name": file_record.bucket_name,
            "object_key": file_record.object_key,
        },
    )
    db.add(job)
    await db.flush()

    payload = {**job.payload_json, "job_id": str(job.id)}
    response = FileDeleteResponse(message="File deleted successfully", file_id=file_record.id)
    return response, PendingFileEvent("image.deleted", payload)
