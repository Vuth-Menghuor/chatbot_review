from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models import ApiKey, ChatThread, Project, User
from app.core.security import hash_password, hash_secret


# Keep timezone-aware timestamps consistent across model factories.
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Build a valid user model without requiring a real database row.
def make_user(**overrides) -> User:
    values = {
        "id": uuid4(),
        "full_name": "Test User",
        "nickname": None,
        "email": "user@example.test",
        "hashed_password": hash_password("password123"),
        "phone": None,
        "address": None,
        "avatar_url": None,
        "role": "user",
        "is_active": True,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    values.update(overrides)
    return User(**values)


# Build an API key model that matches the fields returned by API-key endpoints.
def make_api_key(user_id=None, **overrides) -> ApiKey:
    values = {
        "id": uuid4(),
        "user_id": user_id or uuid4(),
        "key_hash": hash_secret("cb_test_key"),
        "name": "Test key",
        "is_active": True,
        "created_at": utc_now(),
        "last_used_at": None,
    }
    values.update(overrides)
    return ApiKey(**values)


# Build a project model for ownership and endpoint tests.
def make_project(user_id=None, **overrides) -> Project:
    values = {
        "id": uuid4(),
        "user_id": user_id or uuid4(),
        "name": "Project",
        "description": None,
        "color": None,
        "icon": None,
        "status": "active",
        "is_pinned": False,
        "is_archived": False,
        "last_activity_at": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    values.update(overrides)
    return Project(**values)


# Build a chat-thread model for project/chat ownership tests.
def make_chat_thread(user_id=None, project_id=None, **overrides) -> ChatThread:
    values = {
        "id": uuid4(),
        "user_id": user_id or uuid4(),
        "project_id": project_id,
        "title": "New Chat",
        "status": "active",
        "is_pinned": False,
        "is_archived": False,
        "last_message_preview": None,
        "last_activity_at": None,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    values.update(overrides)
    return ChatThread(**values)
