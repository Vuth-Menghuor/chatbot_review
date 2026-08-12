from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    nickname: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=512)
    avatar_url: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class UserRead(ORMModel):
    id: UUID
    full_name: str
    nickname: str | None = None
    email: EmailStr
    phone: str | None = None
    address: str | None = None
    avatar_url: str | None = None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiKeyRead(ORMModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyRead):
    api_key: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    color: str | None = Field(default=None, max_length=32)
    icon: str | None = Field(default=None, max_length=64)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    color: str | None = Field(default=None, max_length=32)
    icon: str | None = Field(default=None, max_length=64)
    is_pinned: bool | None = None
    is_archived: bool | None = None


class ProjectRead(ORMModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    color: str | None
    icon: str | None
    status: str
    is_pinned: bool
    is_archived: bool
    last_activity_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectRead):
    chat_count: int = 0
    recent_chats: list["ChatThreadRead"] = Field(default_factory=list)


class ChatThreadCreate(BaseModel):
    title: str | None = Field(default="New Chat", max_length=255)
    project_id: UUID | None = None


class ChatThreadUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    is_pinned: bool | None = None
    is_archived: bool | None = None
    project_id: UUID | None = None


class ChatThreadRead(ORMModel):
    id: UUID
    user_id: UUID
    project_id: UUID | None
    title: str | None
    status: str
    is_pinned: bool
    is_archived: bool
    last_message_preview: str | None
    last_activity_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChatShareCreate(BaseModel):
    visibility: Literal["private", "public"] = "private"
    client_snapshot: list[Any] = Field(default_factory=list)


class ChatShareRead(ORMModel):
    chat_id: UUID
    token: str
    visibility: Literal["private", "public"]
    title: str | None
    share_url_path: str
    created_at: datetime
    updated_at: datetime


class PublicChatShareRead(BaseModel):
    chat_id: UUID
    token: str
    title: str | None
    messages: list[Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ChatRequest(BaseModel):
    chat_id: UUID | None = None
    project_id: UUID | None = None
    message: str = Field(min_length=1, max_length=100_000)
    attachments: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    presentation: dict[str, Any] | None = None
    context: dict[str, Any] | None = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value


class FeedbackRequest(BaseModel):
    chat_id: UUID
    message_id: str
    rating: Literal["good", "bad"]
    comment: str | None = None


class MessageResponse(BaseModel):
    message: str
