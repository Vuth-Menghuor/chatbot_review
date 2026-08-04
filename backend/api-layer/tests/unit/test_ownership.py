from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import ChatThread, Project
from app.services.ownership import create_or_get_chat, owned_chat, owned_project


# Wrap one fake query result with the SQLAlchemy method used by ownership helpers.
class FakeScalarResult:
    # Store the model that the fake query should return.
    def __init__(self, item):
        self.item = item

    # Match SQLAlchemy's scalar_one_or_none API used in the service.
    def scalar_one_or_none(self):
        return self.item


# Minimal async DB session fake for ownership helpers, without needing Postgres.
class FakeSession:
    # Configure what execute() and get() should return for each test case.
    def __init__(self, *, execute_item=None, get_item=None) -> None:
        self.execute_item = execute_item
        self.get_item = get_item
        self.added = []
        self.flushed = False

    # Simulate session.execute(select(...)).
    async def execute(self, _statement):
        return FakeScalarResult(self.execute_item)

    # Simulate session.get(Model, id).
    async def get(self, _model, _item_id):
        return self.get_item

    # Track newly created models so tests can verify side effects.
    def add(self, item):
        self.added.append(item)

    # Track flush calls because create_or_get_chat must persist new chat IDs.
    async def flush(self):
        self.flushed = True


# Small stand-in for an existing chat when we only need ownership fields.
@dataclass
class ExistingChat:
    id: object
    user_id: object
    project_id: object | None = None
    status: str = "active"


# A project returned by the ownership query should pass through unchanged.
@pytest.mark.asyncio
async def test_owned_project_returns_matching_project():
    project = Project(id=uuid4(), user_id=uuid4(), name="Docs")
    db = FakeSession(execute_item=project)

    assert await owned_project(db, project.id, project.user_id) is project


# Missing or non-owned projects must be hidden behind a 404.
@pytest.mark.asyncio
async def test_owned_project_raises_404_when_missing():
    with pytest.raises(HTTPException) as exc_info:
        await owned_project(FakeSession(execute_item=None), uuid4(), uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Project not found"


# Missing or non-owned chats must be hidden behind a 404.
@pytest.mark.asyncio
async def test_owned_chat_raises_404_when_missing():
    with pytest.raises(HTTPException) as exc_info:
        await owned_chat(FakeSession(execute_item=None), uuid4(), uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Chat not found"


# A user must not attach to an existing chat owned by another user.
@pytest.mark.asyncio
async def test_create_or_get_chat_rejects_existing_chat_owned_by_another_user():
    requested_user_id = uuid4()
    existing_chat = ExistingChat(id=uuid4(), user_id=uuid4())
    db = FakeSession(get_item=existing_chat)

    with pytest.raises(HTTPException) as exc_info:
        await create_or_get_chat(db, requested_user_id, existing_chat.id, None, "hello")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Chat not found"


# When no chat ID is provided, the service should create a new chat for the current user.
@pytest.mark.asyncio
async def test_create_or_get_chat_creates_new_chat_when_no_chat_id_is_provided():
    user_id = uuid4()
    db = FakeSession()

    chat = await create_or_get_chat(db, user_id, None, None, "A long message\nwith a title")

    assert isinstance(chat, ChatThread)
    assert chat.user_id == user_id
    assert chat.title == "A long message with a title"
    assert db.added == [chat]
    assert db.flushed is True
