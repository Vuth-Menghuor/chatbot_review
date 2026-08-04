from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import auth as auth_endpoint
from app.schemas.common import LoginRequest, RefreshRequest, UserCreate
from tests.factories import make_user


# This file verifies auth endpoint functions while replacing the database and rate limiter.


# Query result fake with the SQLAlchemy method used by auth endpoints.
class FakeResult:
    # Store one fake row or scalar value for scalar_one_or_none().
    def __init__(self, value=None) -> None:
        self.value = value

    # Return the configured value as SQLAlchemy would for a single-row query.
    def scalar_one_or_none(self):
        return self.value


# Minimal DB session for register/login/refresh endpoint behavior.
class FakeAuthSession:
    # Configure query results and capture write behavior.
    def __init__(self, *, execute_value=None, get_value=None) -> None:
        self.execute_value = execute_value
        self.get_value = get_value
        self.added = []
        self.committed = False
        self.refreshed = []

    # Return fake select results.
    async def execute(self, _statement):
        return FakeResult(self.execute_value)

    # Return fake primary-key lookup results.
    async def get(self, _model, _item_id):
        return self.get_value

    # Capture inserted users or refresh-token rows.
    def add(self, item):
        self.added.append(item)

    # Simulate database defaults that response models require.
    async def flush(self):
        from uuid import uuid4
        from tests.factories import utc_now

        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "role", None) is None:
                item.role = "user"
            if getattr(item, "is_active", None) is None:
                item.is_active = True
            if getattr(item, "created_at", None) is None:
                item.created_at = utc_now()
            if getattr(item, "updated_at", None) is None:
                item.updated_at = utc_now()

    # Capture commit calls.
    async def commit(self):
        self.committed = True

    # Capture refresh calls.
    async def refresh(self, item):
        self.refreshed.append(item)


# Build the small part of Request used by auth.client_ip().
def fake_request(ip: str = "127.0.0.1"):
    return SimpleNamespace(client=SimpleNamespace(host=ip), state=SimpleNamespace())


# Endpoint rate limiting is tested separately; disable it here.
async def noop_rate_limit(*_args, **_kwargs):
    return None


# Apply shared fakes to every auth endpoint test.
@pytest.fixture(autouse=True)
def patch_external_dependencies(monkeypatch):
    monkeypatch.setattr(auth_endpoint, "enforce_rate_limit", noop_rate_limit)


# Register should create a new user when the email is not already taken.
@pytest.mark.asyncio
async def test_register_success():
    db = FakeAuthSession(execute_value=None)

    response = await auth_endpoint.register(
        UserCreate(full_name="Ada Lovelace", email="ADA@example.com", password="password123"),
        fake_request(),
        db=db,
    )

    assert response.email == "ada@example.com"
    assert db.added[0].email == "ada@example.com"
    assert db.committed is True


# Register should reject duplicate email addresses before creating a user.
@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409():
    db = FakeAuthSession(execute_value=object())

    with pytest.raises(HTTPException) as exc_info:
        await auth_endpoint.register(
            UserCreate(full_name="Ada Lovelace", email="ada@example.com", password="password123"),
            fake_request(),
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Email is already registered"
    assert db.added == []


# Login should return access/refresh tokens for a valid active user.
@pytest.mark.asyncio
async def test_login_success_returns_tokens():
    user = make_user(email="ada@example.com")
    db = FakeAuthSession(execute_value=user)

    response = await auth_endpoint.login(
        LoginRequest(email="ada@example.com", password="password123"),
        fake_request(),
        db=db,
    )

    assert response.token_type == "bearer"
    assert response.access_token
    assert response.refresh_token
    assert response.user.id == user.id
    assert db.committed is True


# Login should reject bad credentials without issuing refresh-token rows.
@pytest.mark.asyncio
async def test_bad_login_returns_401():
    user = make_user(email="ada@example.com")

    with pytest.raises(HTTPException) as exc_info:
        await auth_endpoint.login(
            LoginRequest(email="ada@example.com", password="wrong-password"),
            fake_request(),
            db=FakeAuthSession(execute_value=user),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid email or password"


# /auth/me should return the authenticated user object supplied by the auth dependency.
@pytest.mark.asyncio
async def test_me_returns_current_user():
    user = make_user()

    assert await auth_endpoint.me(user=user) is user


# Invalid refresh tokens should be rejected before issuing new tokens.
@pytest.mark.asyncio
async def test_refresh_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        await auth_endpoint.refresh(RefreshRequest(refresh_token="not-a-jwt"), db=FakeAuthSession())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or expired refresh token"
