from __future__ import annotations

import asyncio
import json
import sys
import types
from types import SimpleNamespace
from uuid import uuid4


class FakeCryptContext:
    def __init__(self, *_args, **_kwargs):
        pass

    def hash(self, value: str) -> str:
        return value

    def verify(self, value: str, hashed: str) -> bool:
        return value == hashed


def install_optional_dependency_fakes() -> None:
    passlib = sys.modules.setdefault("passlib", types.ModuleType("passlib"))
    context = types.ModuleType("passlib.context")
    context.CryptContext = FakeCryptContext
    passlib.context = context
    sys.modules["passlib.context"] = context

    email_validator = sys.modules.setdefault("email_validator", types.ModuleType("email_validator"))
    email_validator.__version__ = "2.0.0"
    import pydantic.networks

    pydantic.networks.version = lambda package: "2.0.0" if package == "email-validator" else "0"


install_optional_dependency_fakes()

from app.api.v1.endpoints import chat as chat_endpoint
from app.schemas.common import ChatRequest
from app.services.main_chatbot_client import parse_orchestrator_sse_block


class FakeChat:
    def __init__(self):
        self.id = uuid4()
        self.project_id = uuid4()


class FakeUser:
    def __init__(self):
        self.id = uuid4()
        self.role = "user"


class FakeDb:
    def __init__(self):
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


class FakeRequest:
    client = SimpleNamespace(host="127.0.0.1")
    state = SimpleNamespace()

    async def is_disconnected(self) -> bool:
        return False


class FakeMainChatbotClient:
    def __init__(self, intent: str = "general"):
        self.intent = intent
        self.calls: list[tuple[str, str, dict]] = []

    async def request(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        return {
            "request_id": f"req-{len(self.calls)}",
            "session_id": kwargs["json"]["session_id"],
            "intent": self.intent,
            "status": "completed",
            "answer": "Upstream answer.",
        }

    async def stream_sse(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        yield "event: done\ndata: " + json.dumps({
            "request_id": f"req-{len(self.calls)}",
            "session_id": kwargs["json"]["session_id"],
            "intent": self.intent,
            "status": "completed",
            "answer": "Upstream answer.",
        })

    async def stream_chat(self, body):
        async for block in self.stream_sse("POST", "/query/stream", json=body):
            parsed = parse_orchestrator_sse_block(block)
            if parsed:
                yield parsed


class FullContractMainChatbotClient(FakeMainChatbotClient):
    async def request(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        return self._payload(kwargs["json"])

    async def stream_sse(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        yield "event: done\ndata: " + json.dumps(self._payload(kwargs["json"]))

    def _payload(self, body: dict):
        return {
            "request_id": "req-contract",
            "session_id": body["session_id"],
            "chat_id": body["chat_id"],
            "project_id": str(body.get("project_id") or ""),
            "intent": self.intent,
            "status": "completed",
            "query": body["question"],
            "language": "en",
            "coverage": "complete",
            "confidence": "high",
            "answer": "Upstream answer.",
            "citations": [],
            "suggestions": ["Ask about import permits"],
            "clarifications": [],
            "errors": [],
            "metrics": {"latency_ms": 321},
        }


def patch_chat_dependencies(monkeypatch, chat: FakeChat, upstream: FakeMainChatbotClient) -> None:
    async def fake_create_or_get_chat(*_args, **_kwargs):
        return chat

    async def fake_touch_chat(*_args, **_kwargs):
        return None

    async def fake_enforce_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(chat_endpoint, "create_or_get_chat", fake_create_or_get_chat)
    monkeypatch.setattr(chat_endpoint, "touch_chat", fake_touch_chat)
    monkeypatch.setattr(chat_endpoint, "enforce_rate_limit", fake_enforce_rate_limit)
    monkeypatch.setattr(chat_endpoint, "add_audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_endpoint, "main_chatbot_client", upstream)


def sent_bodies(upstream: FakeMainChatbotClient) -> list[dict]:
    return [call[2]["json"] for call in upstream.calls]


async def read_sse_events(response) -> list[tuple[str, dict]]:
    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    events: list[tuple[str, dict]] = []
    for block in body.decode().strip().split("\n\n"):
        event = "message"
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            if line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
    return events


def test_send_forwards_calculation_and_followup_raw_with_stable_ids(monkeypatch):
    asyncio.run(_send_forwards_calculation_and_followup_raw_with_stable_ids(monkeypatch))


async def _send_forwards_calculation_and_followup_raw_with_stable_ids(monkeypatch):
    chat = FakeChat()
    upstream = FakeMainChatbotClient(intent="calculation")
    patch_chat_dependencies(monkeypatch, chat, upstream)

    first = "calculate import tax for hs 8703.22.00 cif 10500 USD from China under ACFTA dv=0"
    followup = "1,998 cc"

    await chat_endpoint.send_chat(ChatRequest(message=first), FakeRequest(), user=FakeUser(), db=FakeDb())
    await chat_endpoint.send_chat(ChatRequest(chat_id=chat.id, message=followup), FakeRequest(), user=FakeUser(), db=FakeDb())

    first_body, followup_body = sent_bodies(upstream)
    assert first_body == {
        "question": first,
        "session_id": str(chat.id),
        "chat_id": str(chat.id),
    }
    assert followup_body == {
        "question": followup,
        "session_id": str(chat.id),
        "chat_id": str(chat.id),
    }
    assert first_body["session_id"] == followup_body["session_id"]
    assert first_body["chat_id"] == followup_body["chat_id"]

    followup_json = json.dumps(followup_body)
    assert "Cambodia" not in followup_json
    assert "8703.22.00" not in followup_json
    assert "10500" not in followup_json
    assert "dv=0" not in followup_json


def test_send_forwards_general_retrieval_and_trade_raw(monkeypatch):
    asyncio.run(_send_forwards_general_retrieval_and_trade_raw(monkeypatch))


async def _send_forwards_general_retrieval_and_trade_raw(monkeypatch):
    chat = FakeChat()
    upstream = FakeMainChatbotClient()
    patch_chat_dependencies(monkeypatch, chat, upstream)

    messages = [
        ("general", "What documents do I need to import a car?"),
        ("hs_code_lookup", "Give me the HS code for cotton fabric."),
        ("trade_query", "Show Cambodia exports to Vietnam in 2024."),
    ]

    for intent, message in messages:
        upstream.intent = intent
        await chat_endpoint.send_chat(ChatRequest(chat_id=chat.id, message=message), FakeRequest(), user=FakeUser(), db=FakeDb())

    for body, (_intent, message) in zip(sent_bodies(upstream), messages):
        assert body["question"] == message
        assert body["session_id"] == str(chat.id)
        assert body["chat_id"] == str(chat.id)


def test_send_preserves_generic_presentation_and_context(monkeypatch):
    asyncio.run(_send_preserves_generic_presentation_and_context(monkeypatch))


async def _send_preserves_generic_presentation_and_context(monkeypatch):
    chat = FakeChat()
    upstream = FakeMainChatbotClient(intent="hs_code_lookup")
    patch_chat_dependencies(monkeypatch, chat, upstream)

    presentation = {"preferred_blocks": ["table"], "fallback": "markdown"}
    context = {"reply_to_request_id": "previous-request"}
    await chat_endpoint.send_chat(
        ChatRequest(chat_id=chat.id, message="Cotton fabric", presentation=presentation, context=context),
        FakeRequest(),
        user=FakeUser(),
        db=FakeDb(),
    )

    assert sent_bodies(upstream)[0] == {
        "question": "Cotton fabric",
        "session_id": str(chat.id),
        "chat_id": str(chat.id),
        "presentation": presentation,
        "context": context,
    }


def test_stream_uses_internal_stream_request_contract(monkeypatch):
    asyncio.run(_stream_uses_internal_stream_request_contract(monkeypatch))


async def _stream_uses_internal_stream_request_contract(monkeypatch):
    chat = FakeChat()
    upstream = FakeMainChatbotClient(intent="calculation")
    patch_chat_dependencies(monkeypatch, chat, upstream)

    response = await chat_endpoint.stream_chat(
        ChatRequest(chat_id=chat.id, message="1,998 cc"),
        FakeRequest(),
        user=FakeUser(),
        db=FakeDb(),
    )

    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    assert b"event: start" in body
    assert b"event: done" in body
    assert upstream.calls[0][0:2] == ("POST", "/query/stream")
    sent_body = sent_bodies(upstream)[0]
    assert sent_body == {
        "question": "1,998 cc",
        "session_id": str(chat.id),
        "chat_id": str(chat.id),
        "project_id": str(chat.project_id),
        "request_id": sent_body["request_id"],
    }
    assert sent_body["request_id"]


def test_stream_done_keeps_same_normalized_v1_shape_as_send(monkeypatch):
    asyncio.run(_stream_done_keeps_same_normalized_v1_shape_as_send(monkeypatch))


async def _stream_done_keeps_same_normalized_v1_shape_as_send(monkeypatch):
    chat = FakeChat()
    user = FakeUser()
    message = "What documents do I need to import a car?"

    send_upstream = FullContractMainChatbotClient(intent="general")
    patch_chat_dependencies(monkeypatch, chat, send_upstream)
    send_payload = await chat_endpoint.send_chat(
        ChatRequest(chat_id=chat.id, message=message),
        FakeRequest(),
        user=user,
        db=FakeDb(),
    )

    stream_upstream = FullContractMainChatbotClient(intent="general")
    patch_chat_dependencies(monkeypatch, chat, stream_upstream)
    stream_response = await chat_endpoint.stream_chat(
        ChatRequest(chat_id=chat.id, message=message),
        FakeRequest(),
        user=user,
        db=FakeDb(),
    )
    stream_events = await read_sse_events(stream_response)
    done_payload = next(data for event, data in stream_events if event == "done")

    expected_keys = {
        "api_version",
        "request_id",
        "session_id",
        "chat_id",
        "project_id",
        "status",
        "service",
        "intent",
        "query",
        "language",
        "coverage",
        "confidence",
        "response",
        "message",
        "citations",
        "suggestions",
        "clarifications",
        "errors",
        "metrics",
    }

    assert set(done_payload) == set(send_payload)
    assert expected_keys <= set(done_payload)
    assert done_payload == send_payload
    assert done_payload["api_version"] == "1.0"
    assert "mode" not in done_payload
    assert "transport" not in done_payload
    assert "stream" not in done_payload
    assert isinstance(done_payload["message"]["content"], list)
    assert done_payload["message"] == send_payload["message"]
    assert done_payload["response"] == send_payload["response"]


def test_stream_forwards_future_internal_stream_request_shape(monkeypatch):
    asyncio.run(_stream_forwards_future_internal_stream_request_shape(monkeypatch))


async def _stream_forwards_future_internal_stream_request_shape(monkeypatch):
    chat = FakeChat()
    upstream = FakeMainChatbotClient(intent="hs_code_lookup")
    patch_chat_dependencies(monkeypatch, chat, upstream)
    presentation = {"preferred_blocks": ["table"], "fallback": "markdown"}
    context = {"reply_to_request_id": "previous-request"}

    response = await chat_endpoint.stream_chat(
        ChatRequest(
            chat_id=chat.id,
            message="What is the HS code for a laptop?",
            presentation=presentation,
            context=context,
        ),
        FakeRequest(),
        user=FakeUser(),
        db=FakeDb(),
    )

    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    sent_body = sent_bodies(upstream)[0]
    assert upstream.calls[0][0:2] == ("POST", "/query/stream")
    assert sent_body == {
        "question": "What is the HS code for a laptop?",
        "session_id": str(chat.id),
        "chat_id": str(chat.id),
        "project_id": str(chat.project_id),
        "request_id": sent_body["request_id"],
        "presentation": presentation,
        "context": context,
    }
    assert f'"request_id": "{sent_body["request_id"]}"'.encode() in body
