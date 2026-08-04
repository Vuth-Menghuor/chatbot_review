from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import api_keys as api_keys_endpoint
from app.schemas.common import ApiKeyCreate
from tests.factories import make_api_key, make_user, utc_now


# This file verifies API-key endpoint functions with fake auth and database dependencies.


# Query result fake that supports both scalar_one_or_none() and scalars().all().
class FakeResult:
    # Store rows returned by the fake query.
    def __init__(self, rows=None) -> None:
        self.rows = rows or []

    # Return one row for delete lookups.
    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    # Return self so endpoint code can chain scalars().all().
    def scalars(self):
        return self

    # Return all rows for list endpoints.
    def all(self):
        return self.rows


# Minimal DB session for API-key endpoint behavior.
class FakeApiKeySession:
    # Configure query rows and capture write side effects.
    def __init__(self, *, rows=None) -> None:
        self.rows = rows or []
        self.added = []
        self.flushed = False
        self.committed = False
        self.refreshed = []

    # Capture inserted API-key rows.
    def add(self, item):
        self.added.append(item)

    # Simulate database defaults on inserted rows.
    async def flush(self):
        self.flushed = True
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "is_active", None) is None:
                item.is_active = True
            if getattr(item, "created_at", None) is None:
                item.created_at = utc_now()

    # Capture transaction commits.
    async def commit(self):
        self.committed = True

    # Capture refresh calls before response serialization.
    async def refresh(self, item):
        self.refreshed.append(item)

    # Return fake query rows.
    async def execute(self, _statement):
        return FakeResult(self.rows)


# Avoid audit-log DB writes in endpoint tests.
def noop_add_audit_log(*_args, **_kwargs):
    return None


# Apply shared fakes to every API-key endpoint test.
@pytest.fixture(autouse=True)
def patch_external_dependencies(monkeypatch):
    monkeypatch.setattr(api_keys_endpoint, "add_audit_log", noop_add_audit_log)


# Creating an API key should return the raw key once and persist a hashed row.
@pytest.mark.asyncio
async def test_create_api_key_endpoint():
    user = make_user()
    db = FakeApiKeySession()

    response = await api_keys_endpoint.create_api_key(ApiKeyCreate(name="Frontend"), user=user, db=db)

    assert response.name == "Frontend"
    assert response.api_key.startswith("cb_")
    assert db.added[0].user_id == user.id
    assert db.committed is True


# Listing API keys should return the fake rows produced by the user-scoped query.
@pytest.mark.asyncio
async def test_list_api_keys_endpoint():
    user = make_user()
    rows = [make_api_key(user_id=user.id, name="Frontend")]

    response = await api_keys_endpoint.list_api_keys(user=user, db=FakeApiKeySession(rows=rows))

    assert response == rows


# Deleting an API key should soft-disable the key and commit the transaction.
@pytest.mark.asyncio
async def test_delete_api_key_endpoint():
    user = make_user()
    item = make_api_key(user_id=user.id)
    db = FakeApiKeySession(rows=[item])

    response = await api_keys_endpoint.delete_api_key(item.id, user=user, db=db)

    assert response == {"message": "API key disabled"}
    assert item.is_active is False
    assert db.committed is True


# Missing or non-owned API keys should return 404.
@pytest.mark.asyncio
async def test_delete_missing_api_key_endpoint_returns_404():
    user = make_user()

    with pytest.raises(HTTPException) as exc_info:
        await api_keys_endpoint.delete_api_key(uuid4(), user=user, db=FakeApiKeySession(rows=[]))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "API key not found"
