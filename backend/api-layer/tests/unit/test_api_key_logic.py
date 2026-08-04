from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import api_keys
from app.core.security import hash_secret
from app.schemas.common import ApiKeyCreate
from tests.factories import make_api_key, make_user, utc_now


# This file protects API-key endpoint logic until it is moved into a service/repository layer.


# Wrap fake query results with the SQLAlchemy methods used by the endpoint functions.
class FakeScalarResult:
    # Store rows returned by a fake select query.
    def __init__(self, items):
        self.items = items

    # Support delete_api_key, which expects one row or None.
    def scalar_one_or_none(self):
        return self.items[0] if self.items else None

    # Support list_api_keys, which chains scalars().all().
    def scalars(self):
        return self

    # Return all fake rows from list-style endpoint queries.
    def all(self):
        return self.items


# Minimal async session fake for endpoint logic without a real database.
class FakeSession:
    # Configure query rows and capture write side effects for assertions.
    def __init__(self, *, execute_items=None) -> None:
        self.execute_items = execute_items or []
        self.added = []
        self.committed = False
        self.flushed = False
        self.refreshed = []

    # Capture inserted models.
    def add(self, item):
        self.added.append(item)

    # Simulate database defaults assigned during flush.
    async def flush(self):
        self.flushed = True
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "is_active", None) is None:
                item.is_active = True
            if getattr(item, "created_at", None) is None:
                item.created_at = utc_now()

    # Capture refresh calls made before returning response models.
    async def refresh(self, item):
        self.refreshed.append(item)

    # Capture transaction commits.
    async def commit(self):
        self.committed = True

    # Return fake select results.
    async def execute(self, _statement):
        return FakeScalarResult(self.execute_items)


# Creating an API key should return the raw key once while storing only its hash.
@pytest.mark.asyncio
async def test_create_api_key_returns_raw_key_once_and_stores_only_hash(monkeypatch):
    user = make_user()
    db = FakeSession()
    audit_logs = []

    monkeypatch.setattr(api_keys, "generate_api_key", lambda: "cb_raw_secret")
    monkeypatch.setattr(api_keys, "add_audit_log", lambda *args, **kwargs: audit_logs.append((args, kwargs)))

    response = await api_keys.create_api_key(ApiKeyCreate(name="Frontend"), user=user, db=db)

    created_item = db.added[0]
    assert response.api_key == "cb_raw_secret"
    assert response.name == "Frontend"
    assert created_item.user_id == user.id
    assert created_item.key_hash == hash_secret("cb_raw_secret")
    assert created_item.key_hash != "cb_raw_secret"
    assert db.flushed is True
    assert db.committed is True
    assert db.refreshed == [created_item]
    assert audit_logs


# Listing API keys should return the rows produced by the user-scoped query.
@pytest.mark.asyncio
async def test_list_api_keys_returns_only_query_results():
    user = make_user()
    rows = [
        make_api_key(user_id=user.id, name="First"),
        make_api_key(user_id=user.id, name="Second", key_hash=hash_secret("another")),
    ]

    response = await api_keys.list_api_keys(user=user, db=FakeSession(execute_items=rows))

    assert response == rows


# Deleting an API key should disable it instead of removing the row.
@pytest.mark.asyncio
async def test_delete_api_key_marks_key_inactive_and_commits(monkeypatch):
    user = make_user()
    item = make_api_key(user_id=user.id)
    db = FakeSession(execute_items=[item])
    audit_logs = []
    monkeypatch.setattr(api_keys, "add_audit_log", lambda *args, **kwargs: audit_logs.append((args, kwargs)))

    response = await api_keys.delete_api_key(item.id, user=user, db=db)

    assert response == {"message": "API key disabled"}
    assert item.is_active is False
    assert db.committed is True
    assert audit_logs


# A missing or non-owned API key should return 404.
@pytest.mark.asyncio
async def test_delete_api_key_returns_404_when_key_is_not_owned():
    user = make_user()

    with pytest.raises(HTTPException) as exc_info:
        await api_keys.delete_api_key(uuid4(), user=user, db=FakeSession(execute_items=[]))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "API key not found"
