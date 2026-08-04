from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.endpoints import chat as chat_endpoint
from app.schemas.common import ChatRequest
from tests.factories import make_chat_thread, make_user


# This file verifies chat endpoint functions while faking the DB, rate limiter, and orchestrator.


# Minimal DB session for chat send tests.
class FakeChatSession:
    # Capture commits made after chat metadata is touched.
    def __init__(self) -> None:
        self.committed = False

    # Capture transaction commits.
    async def commit(self):
        self.committed = True


# Fake orchestrator client for /chat/send.
class FakeMainChatbotClient:
    # Configure the upstream response returned to the API layer.
    def __init__(self, result) -> None:
        self.result = result
        self.calls = []

    # Capture request details and return the configured fake response.
    async def request(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.result


# Build the small part of Request used by rate-limit logging.
def fake_request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), state=SimpleNamespace())


# Disable endpoint rate limiting for deterministic chat tests.
async def noop_rate_limit(*_args, **_kwargs):
    return None


# Avoid audit-log DB writes in chat endpoint tests.
def noop_add_audit_log(*_args, **_kwargs):
    return None


# Apply shared external-service fakes to every chat endpoint test.
@pytest.fixture(autouse=True)
def patch_external_dependencies(monkeypatch):
    monkeypatch.setattr(chat_endpoint, "enforce_rate_limit", noop_rate_limit)
    monkeypatch.setattr(chat_endpoint, "add_audit_log", noop_add_audit_log)


# Blank messages should fail request validation before reaching the orchestrator.
def test_chat_request_rejects_blank_message():
    with pytest.raises(ValidationError):
        ChatRequest(message="   ")


# A normal chat send should create/touch a chat, call the orchestrator, and normalize the response.
@pytest.mark.asyncio
async def test_send_chat_returns_normalized_response(monkeypatch):
    user = make_user()
    chat = make_chat_thread(user_id=user.id)
    db = FakeChatSession()
    upstream = FakeMainChatbotClient(
        {
            "request_id": "req-chat",
            "session_id": str(chat.id),
            "intent": "general",
            "answer": "Hello from upstream.",
        }
    )

    async def fake_create_or_get_chat(*_args, **_kwargs):
        return chat

    async def fake_touch_chat(*_args, **_kwargs):
        return None

    monkeypatch.setattr(chat_endpoint, "create_or_get_chat", fake_create_or_get_chat)
    monkeypatch.setattr(chat_endpoint, "touch_chat", fake_touch_chat)
    monkeypatch.setattr(chat_endpoint, "main_chatbot_client", upstream)

    response = await chat_endpoint.send_chat(ChatRequest(message="hello"), fake_request(), user=user, db=db)

    assert response["request_id"] == "req-chat"
    assert response["chat_id"] == str(chat.id)
    assert response["message"]["content"][0]["type"] == "markdown"
    assert upstream.calls[0][0:2] == ("POST", "/query")
    assert db.committed is True


# Failed orchestrator-style payloads should become normalized failed responses with an error block.
@pytest.mark.asyncio
async def test_send_chat_normalizes_failed_orchestrator_payload(monkeypatch):
    user = make_user()
    chat = make_chat_thread(user_id=user.id)
    upstream = FakeMainChatbotClient(
        {
            "status": "failed",
            "error": {"message": "Main chatbot service is unavailable"},
        }
    )

    async def fake_create_or_get_chat(*_args, **_kwargs):
        return chat

    async def fake_touch_chat(*_args, **_kwargs):
        return None

    monkeypatch.setattr(chat_endpoint, "create_or_get_chat", fake_create_or_get_chat)
    monkeypatch.setattr(chat_endpoint, "touch_chat", fake_touch_chat)
    monkeypatch.setattr(chat_endpoint, "main_chatbot_client", upstream)

    response = await chat_endpoint.send_chat(ChatRequest(message="hello"), fake_request(), user=user, db=FakeChatSession())

    assert response["status"] == "failed"
    assert response["message"]["content"][0]["type"] == "error"
    assert response["message"]["content"][0]["message"] == "Main chatbot service is unavailable"


# Project/chat ownership mismatches should surface as client errors before orchestrator calls.
@pytest.mark.asyncio
async def test_send_chat_returns_project_mismatch_error(monkeypatch):
    user = make_user()

    async def fake_create_or_get_chat(*_args, **_kwargs):
        raise HTTPException(status_code=400, detail="project_id does not match the chat's project")

    monkeypatch.setattr(chat_endpoint, "create_or_get_chat", fake_create_or_get_chat)

    with pytest.raises(HTTPException) as exc_info:
        await chat_endpoint.send_chat(
            ChatRequest(chat_id=uuid4(), project_id=uuid4(), message="hello"),
            fake_request(),
            user=user,
            db=FakeChatSession(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "project_id does not match the chat's project"
