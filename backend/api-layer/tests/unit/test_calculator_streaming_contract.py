from __future__ import annotations

import json
import asyncio
import sys
import types
from uuid import uuid4

import httpx


class FakeCryptContext:
    def __init__(self, *_args, **_kwargs):
        pass

    def hash(self, value: str) -> str:
        return value

    def verify(self, value: str, hashed: str) -> bool:
        return value == hashed


def install_optional_auth_dependency_fakes() -> None:
    passlib = sys.modules.setdefault("passlib", types.ModuleType("passlib"))
    context = types.ModuleType("passlib.context")
    context.CryptContext = FakeCryptContext
    passlib.context = context
    sys.modules["passlib.context"] = context

    email_validator = sys.modules.setdefault("email_validator", types.ModuleType("email_validator"))
    email_validator.__version__ = "2.0.0"
    import pydantic.networks

    pydantic.networks.version = lambda package: "2.0.0" if package == "email-validator" else "0"


class FakeChat:
    def __init__(self):
        self.id = uuid4()
        self.project_id = uuid4()


class FakeUser:
    def __init__(self):
        self.id = uuid4()
        self.role = "user"


class FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


class FakeDb:
    async def commit(self) -> None:
        return None


class FakeMainChatbotClient:
    def __init__(self, result=None, exc: Exception | None = None):
        self.result = result
        self.exc = exc

    async def request(self, *_args, **_kwargs):
        if self.exc:
            raise self.exc
        return self.result


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
        events.append((event, json.loads("\n".join(data_lines))))
    return events


async def call_stream_chat(monkeypatch, upstream):
    install_optional_auth_dependency_fakes()
    from app.api.v1.endpoints import chat as chat_endpoint
    from app.schemas.common import ChatRequest

    chat = FakeChat()

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

    response = await chat_endpoint.stream_chat(
        ChatRequest(message="calculate petroleum import tax"),
        FakeRequest(),
        user=FakeUser(),
        db=FakeDb(),
    )
    return await read_sse_events(response)


def test_stream_chat_sends_start_then_final_normalized_calculator_done(monkeypatch):
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                result={
                    "request_id": "upstream-calculator-request",
                    "session_id": "upstream-session",
                    "intent": "calculation",
                    "status": "completed",
                    "answer": "Petroleum calculation complete.",
                    "calculator_result": {
                        "summary": {"total_tax": 2500000, "currency": "KHR"},
                        "tax_breakdown": [
                            {"component": "Phase 1", "amount": 1200000, "currency": "KHR"},
                        ],
                    },
                },
            ),
        )
    )

    assert [event for event, _data in events] == ["start", "done"]
    start = events[0][1]
    done = events[1][1]

    assert start["chat_id"]
    assert start["request_id"]
    assert done["api_version"] == "1.0"
    assert done["service"] == "calculator"
    assert done["intent"] == "calculation"
    assert [block["type"] for block in done["message"]["content"]] == ["summary", "table"]
    assert done["message"]["content"][0]["data"]["total_tax"] == 2500000
    assert done["message"]["content"][1]["rows"][0]["amount"] == 1200000
    assert not any(event == "token" for event, _data in events)
    assert not any("table" in data for event, data in events if event != "done")


def test_stream_chat_sends_start_then_final_normalized_general_done_without_fake_tokens(monkeypatch):
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                result={
                    "request_id": "upstream-general-request",
                    "session_id": "upstream-session",
                    "intent": "general",
                    "status": "completed",
                    "answer": "General answer from the upstream service.",
                    "suggestions": ["Ask about import documents"],
                },
            ),
        )
    )

    assert [event for event, _data in events] == ["start", "done"]
    done = events[1][1]

    assert done["api_version"] == "1.0"
    assert done["service"] == "general"
    assert done["intent"] == "general"
    assert [block["type"] for block in done["message"]["content"]] == ["markdown", "suggestions"]
    assert done["message"]["content"][0]["text"] == "General answer from the upstream service."
    assert done["message"]["content"][1]["title"] == "Suggested follow-ups"
    assert not any(event == "token" for event, _data in events)


def test_stream_chat_sends_start_then_final_normalized_retrieval_done_without_partial_blocks(monkeypatch):
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                result={
                    "request_id": "upstream-retrieval-request",
                    "session_id": "upstream-session",
                    "intent": "hs_code_lookup",
                    "status": "clarification_required",
                    "answer": "Candidate HS codes are preliminary.",
                    "table": {
                        "title": "Possible HS Code Matches",
                        "rows": [{"hs_code": "5208.39.00", "description": "Other dyed woven cotton fabrics"}],
                    },
                    "clarifications": ["What is the fabric weight in g/m²?"],
                },
            ),
        )
    )

    assert [event for event, _data in events] == ["start", "done"]
    done = events[1][1]

    assert done["api_version"] == "1.0"
    assert done["service"] == "retrieval"
    assert done["intent"] == "hs_code_lookup"
    assert done["status"] == "clarification_required"
    assert [block["type"] for block in done["message"]["content"]] == ["markdown", "table", "clarification"]
    assert done["message"]["content"][0]["text"] == "Candidate HS codes are preliminary."
    assert done["message"]["content"][1]["rows"][0]["hs_code"] == "5208.39.00"
    assert done["message"]["content"][2]["questions"] == ["What is the fabric weight in g/m²?"]
    assert not any(event == "token" for event, _data in events)
    assert not any(
        "message" in data or "table" in data or "prediction" in data
        for event, data in events
        if event != "done"
    )


def test_stream_chat_sends_start_then_final_normalized_trade_done_without_fake_tokens_or_partial_blocks(monkeypatch):
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                result={
                    "request_id": "upstream-trade-request",
                    "session_id": "upstream-session",
                    "intent": "trade_query",
                    "status": "completed",
                    "answer": "Cambodia's top export partners in 2024 are shown below.",
                    "table": {
                        "title": "Top Export Partners",
                        "columns": [
                            {"key": "partner_country", "label": "Partner Country"},
                            {"key": "value_usd", "label": "Value USD"},
                        ],
                        "rows": [
                            {"partner_country": "Vietnam", "value_usd": 1200000},
                            {"partner_country": "Thailand", "value_usd": 900000},
                        ],
                    },
                    "visualization": {
                        "type": "bar",
                        "title": "Exports by Partner",
                        "labels": ["Vietnam", "Thailand"],
                        "datasets": [{"label": "Value USD", "data": [1200000, 900000]}],
                    },
                },
            ),
        )
    )

    assert [event for event, _data in events] == ["start", "done"]
    start = events[0][1]
    done = events[1][1]

    assert start["chat_id"]
    assert start["request_id"]
    assert done["api_version"] == "1.0"
    assert done["service"] == "trade"
    assert done["intent"] == "trade_query"
    assert [block["type"] for block in done["message"]["content"]] == ["markdown", "table", "chart"]
    assert done["message"]["content"][0]["text"] == "Cambodia's top export partners in 2024 are shown below."
    assert done["message"]["content"][1]["rows"] == [
        {"partner_country": "Vietnam", "value_usd": 1200000},
        {"partner_country": "Thailand", "value_usd": 900000},
    ]
    assert done["message"]["content"][2]["data"]["data"] == [
        {"label": "Vietnam", "value_usd": 1200000},
        {"label": "Thailand", "value_usd": 900000},
    ]
    assert not any(event == "token" for event, _data in events)
    assert not any(
        "message" in data or "table" in data or "visualization" in data or "chart" in data
        for event, data in events
        if event != "done"
    )


def test_stream_chat_sends_safe_error_event_without_raw_internal_details(monkeypatch):
    request = httpx.Request("POST", "http://orchestrator.internal/query")
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(exc=httpx.RequestError("Traceback http://db.internal secret", request=request)),
        )
    )

    assert [event for event, _data in events] == ["start", "error"]
    error = events[1][1]

    assert error == {"detail": "Main Chatbot Service is temporarily unavailable"}
    assert "Traceback" not in json.dumps(error)
    assert "db.internal" not in json.dumps(error)
    assert "secret" not in json.dumps(error)
