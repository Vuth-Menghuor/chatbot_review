from __future__ import annotations

import json
import asyncio
import sys
import types
from uuid import uuid4

import httpx
from fastapi import HTTPException
import pytest

from app.services.main_chatbot_client import ChatStreamEvent, parse_orchestrator_sse_block


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


class SequenceDisconnectRequest:
    def __init__(self, states: list[bool]):
        self.states = states
        self.calls = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        if self.states:
            return self.states.pop(0)
        return False


class FakeDb:
    async def commit(self) -> None:
        return None


class FakeMainChatbotClient:
    def __init__(
        self,
        result=None,
        exc: Exception | None = None,
        events: list[tuple[str, dict]] | None = None,
        stream_exc: Exception | None = None,
    ):
        self.result = result
        self.exc = exc
        self.events = events
        self.stream_exc = stream_exc
        self.calls: list[tuple[str, str, dict]] = []

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if self.exc:
            raise self.exc
        return self.result

    async def stream_sse(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if self.stream_exc or self.exc:
            raise self.stream_exc or self.exc
        events = self.events or [("done", self.result)]
        for event, data in events:
            yield f"event: {event}\ndata: {json.dumps(data)}"

    async def stream_chat(self, body):
        async for block in self.stream_sse("POST", "/query/stream", json=body):
            parsed = parse_orchestrator_sse_block(block)
            if parsed:
                yield parsed


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


async def build_stream_response(monkeypatch, upstream):
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

    return await chat_endpoint.stream_chat(
        ChatRequest(message="calculate petroleum import tax"),
        FakeRequest(),
        user=FakeUser(),
        db=FakeDb(),
    )


async def build_stream_response_with_request(monkeypatch, upstream, request):
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

    return await chat_endpoint.stream_chat(
        ChatRequest(message="calculate petroleum import tax"),
        request,
        user=FakeUser(),
        db=FakeDb(),
    )


class ClosableStreamingClient:
    def __init__(self):
        self.closed = False
        self.yielded = 0

    def stream_chat(self, _body):
        return ClosableUpstreamIterator(self)


class ClosableUpstreamIterator:
    def __init__(self, client: ClosableStreamingClient):
        self.client = client

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.client.yielded += 1
        if self.client.yielded == 1:
            return ChatStreamEvent(type="delta", content="partial")
        if self.client.yielded == 2:
            return ChatStreamEvent(type="delta", content="should not be consumed")
        raise StopAsyncIteration

    async def aclose(self):
        self.client.closed = True


class InterruptingStreamingClient:
    async def stream_chat(self, _body):
        yield ChatStreamEvent(type="delta", content="partial text before failure")
        raise RuntimeError("upstream socket closed unexpectedly")


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
    assert start["status"] == "processing"
    assert "content" not in start
    assert done["api_version"] == "1.0"
    assert done["service"] == "calculator"
    assert done["intent"] == "calculation"
    assert [block["type"] for block in done["message"]["content"]] == ["summary", "table"]
    assert done["message"]["content"][0]["data"]["total_tax"] == 2500000
    assert done["message"]["content"][1]["rows"][0]["amount"] == 1200000
    assert not any(event in {"token", "delta"} for event, _data in events)
    assert not any("table" in data for event, data in events if event != "done")


def test_stream_chat_returns_sse_response_with_required_proxy_headers(monkeypatch):
    response = asyncio.run(
        build_stream_response(
            monkeypatch,
            FakeMainChatbotClient(
                result={
                    "request_id": "upstream-calculator-request",
                    "session_id": "upstream-session",
                    "intent": "calculation",
                    "status": "completed",
                    "answer": "Petroleum calculation complete.",
                },
            ),
        )
    )

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"


def test_stream_chat_closes_upstream_stream_when_client_disconnects(monkeypatch):
    upstream = ClosableStreamingClient()
    request = SequenceDisconnectRequest([False, True])
    response = asyncio.run(build_stream_response_with_request(monkeypatch, upstream, request))

    events = asyncio.run(read_sse_events(response))

    assert [event for event, _data in events] == ["start"]
    assert upstream.yielded == 0
    assert upstream.closed is True
    assert request.calls == 2


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
    assert events[0][1]["status"] == "processing"
    done = events[1][1]

    assert done["api_version"] == "1.0"
    assert done["service"] == "general"
    assert done["intent"] == "general"
    assert [block["type"] for block in done["message"]["content"]] == ["markdown", "suggestions"]
    assert done["message"]["content"][0]["text"] == "General answer from the upstream service."
    assert done["message"]["content"][1]["title"] == "Suggested follow-ups"
    assert not any(event in {"token", "delta"} for event, _data in events)


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
    assert events[0][1]["status"] == "processing"
    done = events[1][1]

    assert done["api_version"] == "1.0"
    assert done["service"] == "retrieval"
    assert done["intent"] == "hs_code_lookup"
    assert done["status"] == "clarification_required"
    assert [block["type"] for block in done["message"]["content"]] == ["markdown", "table", "clarification"]
    assert done["message"]["content"][0]["text"] == "Candidate HS codes are preliminary."
    assert done["message"]["content"][1]["rows"][0]["hs_code"] == "5208.39.00"
    assert done["message"]["content"][2]["questions"] == ["What is the fabric weight in g/m²?"]
    assert not any(event in {"token", "delta"} for event, _data in events)
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
    assert start["status"] == "processing"
    assert "content" not in start
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
    assert not any(event in {"token", "delta"} for event, _data in events)
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


def test_stream_chat_returns_http_503_when_failure_happens_before_sse_response_begins(monkeypatch):
    async def failing_rate_limit(*_args, **_kwargs):
        raise HTTPException(status_code=503, detail="Main Chatbot Service is temporarily unavailable")

    async def fake_create_or_get_chat(*_args, **_kwargs):
        return FakeChat()

    install_optional_auth_dependency_fakes()
    from app.api.v1.endpoints import chat as chat_endpoint
    from app.schemas.common import ChatRequest

    monkeypatch.setattr(chat_endpoint, "enforce_rate_limit", failing_rate_limit)
    monkeypatch.setattr(chat_endpoint, "create_or_get_chat", fake_create_or_get_chat)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            chat_endpoint.stream_chat(
                ChatRequest(message="calculate petroleum import tax"),
                FakeRequest(),
                user=FakeUser(),
                db=FakeDb(),
            )
        )

    assert exc_info.value.status_code == 503


def test_stream_chat_sends_error_event_when_upstream_fails_after_sse_response_begins(monkeypatch):
    events = asyncio.run(call_stream_chat(monkeypatch, InterruptingStreamingClient()))

    assert [event for event, _data in events] == ["start", "delta", "error"]
    assert events[1][1] == {"content": "partial text before failure"}
    assert events[2][1] == {"detail": "Main Chatbot Service stream interrupted"}


def test_stream_chat_converts_clarification_with_questions_to_terminal_done(monkeypatch):
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                events=[
                    (
                        "clarification",
                        {
                            "request_id": "upstream-clarification",
                            "session_id": "upstream-session",
                            "intent": "hs_code_lookup",
                            "message": "I need more information about the product.",
                            "questions": ["What product are you importing?"],
                        },
                    ),
                ],
            ),
        )
    )
    event_names = [event for event, _data in events]
    done = events[-1][1]

    assert event_names == ["start", "done"]
    assert "delta" not in event_names
    assert done["api_version"] == "1.0"
    assert done["status"] == "clarification_required"
    assert done["message"]["content"][0]["text"] == "I need more information about the product."
    assert done["message"]["content"][-1]["type"] == "clarification"
    assert done["message"]["content"][-1]["questions"] == ["What product are you importing?"]


def test_stream_chat_logs_and_errors_for_clarification_with_empty_questions(monkeypatch, caplog):
    caplog.set_level("ERROR")
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                events=[
                    (
                        "clarification",
                        {
                            "request_id": "upstream-empty-clarification",
                            "session_id": "upstream-session",
                            "intent": "hs_code_lookup",
                            "message": "I need more information.",
                            "questions": [],
                        },
                    ),
                ],
            ),
        )
    )

    assert [event for event, _data in events] == ["start", "error"]
    assert events[-1][1] == {"detail": "Main Chatbot Service stream interrupted"}
    assert "upstream_contract_inconsistency empty_clarification_questions" in caplog.text


def test_stream_chat_never_emits_empty_delta(monkeypatch):
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                events=[
                    ("delta", {"content": ""}),
                    ("message", {"chunk": ""}),
                    (
                        "done",
                        {
                            "request_id": "upstream-empty-delta",
                            "session_id": "upstream-session",
                            "intent": "general",
                            "status": "completed",
                            "answer": "Final answer.",
                        },
                    ),
                ],
            ),
        )
    )

    assert [event for event, _data in events] == ["start", "done"]
    assert not any(event == "delta" and data.get("content") == "" for event, data in events)
    assert events[-1][1]["status"] == "completed"


def test_stream_chat_emits_terminal_error_when_upstream_ends_without_done_or_error(monkeypatch):
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                events=[
                    ("delta", {"content": "partial"}),
                ],
            ),
        )
    )

    assert [event for event, _data in events] == ["start", "delta", "error"]
    assert events[-1][1] == {"detail": "Main Chatbot Service stream interrupted"}


def test_stream_chat_proxies_real_upstream_delta_events(monkeypatch):
    upstream = FakeMainChatbotClient(
        events=[
            ("delta", {"content": "Hello, "}),
            ("message", {"chunk": "how can I help?"}),
            (
                "done",
                {
                    "request_id": "upstream-general-request",
                    "session_id": "upstream-session",
                    "intent": "hs_code_lookup",
                    "status": "completed",
                    "answer": "Hello, how can I help?",
                },
            ),
        ]
    )
    events = asyncio.run(call_stream_chat(monkeypatch, upstream))
    streamed_text = "".join(data["content"] for event, data in events if event == "delta")
    done = events[-1][1]

    assert [event for event, _data in events] == ["start", "delta", "delta", "done"]
    assert events[1][1] == {"content": "Hello, "}
    assert events[2][1] == {"content": "how can I help?"}
    assert streamed_text == "Hello, how can I help?"
    assert done["status"] == "completed"
    assert done["message"]["content"]
    assert done["message"]["content"][0]["text"] == "Hello, how can I help?"
    assert upstream.calls[0][0:2] == ("POST", "/query/stream")


def test_stream_chat_emits_only_core_sse_event_types(monkeypatch):
    upstream = FakeMainChatbotClient(
        events=[
            ("start", {"request_id": "upstream-start"}),
            ("progress", {"stage": "retrieving", "message": "Searching customs documents..."}),
            ("retrieval_started", {"collection": "documents"}),
            (
                "done",
                {
                    "request_id": "upstream-general-request",
                    "session_id": "upstream-session",
                    "intent": "general",
                    "status": "completed",
                    "answer": "Final answer.",
                },
            ),
        ]
    )
    events = asyncio.run(call_stream_chat(monkeypatch, upstream))

    assert [event for event, _data in events] == ["start", "done"]
    assert set(event for event, _data in events) <= {"start", "delta", "done", "error"}
    assert "progress" not in {event for event, _data in events}


def test_stream_chat_does_not_emit_structured_renderer_json_as_delta(monkeypatch):
    upstream = FakeMainChatbotClient(
        events=[
            ("delta", {"content": {"type": "table", "rows": []}}),
            ("message", {"chunk": {"type": "chart", "data": {}}}),
            (
                "done",
                {
                    "request_id": "upstream-structured-request",
                    "session_id": "upstream-session",
                    "status": "completed",
                    "answer": "Structured data is available in the final response.",
                    "intent": "hs_code_lookup",
                    "table": {
                        "title": "Possible HS Codes",
                        "rows": [{"hs_code": "8471.30.00"}],
                    },
                    "citations": [
                        {
                            "id": "doc-1",
                            "title": "HS reference",
                            "snippet": "Portable automatic data processing machines",
                        }
                    ],
                },
            ),
        ]
    )
    events = asyncio.run(call_stream_chat(monkeypatch, upstream))

    assert [event for event, _data in events] == ["start", "done"]
    done = events[-1][1]
    assert done["api_version"] == "1.0"
    assert [block["type"] for block in done["message"]["content"]] == ["markdown", "table"]
    assert done["citations"][0]["id"] == "doc-1"


def test_stream_chat_done_event_is_always_normalized_v1(monkeypatch):
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                result={
                    "request_id": "upstream-minimal-request",
                    "session_id": "upstream-session",
                    "intent": "general",
                    "status": "completed",
                    "message": "Minimal upstream final response.",
                },
            ),
        )
    )

    done = events[-1][1]

    assert events[-1][0] == "done"
    assert done["api_version"] == "1.0"
    assert done["request_id"] == "upstream-minimal-request"
    assert done["status"] == "completed"
    assert done["response"]["content"] == "Minimal upstream final response."
    assert done["message"]["role"] == "assistant"
    assert done["message"]["content"][0] == {
        "type": "markdown",
        "text": "Minimal upstream final response.",
    }


def test_stream_chat_does_not_split_complete_done_answer_into_fake_deltas(monkeypatch):
    answer = "The applicable HS code for this product is 8471.30.00."
    events = asyncio.run(
        call_stream_chat(
            monkeypatch,
            FakeMainChatbotClient(
                events=[
                    (
                        "done",
                        {
                            "request_id": "upstream-complete-answer",
                            "session_id": "upstream-session",
                            "intent": "general",
                            "status": "completed",
                            "answer": answer,
                        },
                    ),
                ],
            ),
        )
    )

    assert [event for event, _data in events] == ["start", "done"]
    assert not any(event == "delta" for event, _data in events)
    assert events[-1][1]["response"]["content"] == answer


def test_stream_chat_falls_back_to_query_without_fake_deltas_when_stream_endpoint_missing(monkeypatch):
    stream_request = httpx.Request("POST", "http://orchestrator.internal/query/stream")
    stream_response = httpx.Response(404, request=stream_request, json={"detail": "not found"})
    upstream = FakeMainChatbotClient(
        stream_exc=httpx.HTTPStatusError("not found", request=stream_request, response=stream_response),
        result={
            "request_id": "upstream-query-request",
            "session_id": "upstream-session",
            "intent": "general",
            "status": "completed",
            "answer": "Complete fallback answer from /query.",
        },
    )
    events = asyncio.run(call_stream_chat(monkeypatch, upstream))
    event_names = [event for event, _data in events]

    assert event_names == ["start", "done"]
    assert [call[0:2] for call in upstream.calls] == [
        ("POST", "/query/stream"),
        ("POST", "/query"),
    ]
    assert "delta" not in event_names
    assert events[-1][1]["api_version"] == "1.0"
    assert events[-1][1]["response"]["content"] == "Complete fallback answer from /query."
