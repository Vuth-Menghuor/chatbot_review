from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FileResponse(ORMModel):
    id: UUID
    user_id: UUID
    bucket_name: str
    object_key: str
    original_name: str
    content_type: str
    size_bytes: int
    file_type: str
    status: str
    public_url: str | None
    created_at: datetime
    updated_at: datetime


class FileDetailResponse(FileResponse):
    deleted_at: datetime | None = None


class FileUploadResponse(BaseModel):
    file_id: UUID
    object_key: str
    bucket: str
    status: str
    url: str | None = None


class FileUpdateResponse(BaseModel):
    file_id: UUID
    object_key: str
    bucket: str
    status: str
    url: str | None = None
    message: str = "Image updated successfully"


class FileDeleteResponse(BaseModel):
    message: str
    file_id: UUID
