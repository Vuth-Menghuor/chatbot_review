from __future__ import annotations

import asyncio
import json
import sys
import types
from uuid import uuid4

import httpx

from app.services.main_chatbot_client import ChatStreamEvent, parse_orchestrator_sse_block


class FakeCryptContext:
    def __init__(self, *_args, **_kwargs):
        pass


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
    id = uuid4()
    project_id = uuid4()


class FakeUser:
    id = uuid4()
    role = "user"


class FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


class FakeDb:
    async def commit(self) -> None:
        return None


class FakeClient:
    def __init__(self, events=None, result=None, stream_error=None):
        self.events = events or []
        self.result = result
        self.stream_error = stream_error
        self.calls = []

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.result

    async def stream_chat(self, body):
        self.calls.append(("POST", "/query/stream", {"json": body}))
        if self.stream_error:
            raise self.stream_error
        for event_type, data in self.events:
            yield ChatStreamEvent(type=event_type, content=data if isinstance(data, str) else None, data=data if isinstance(data, dict) else None)


async def stream_events(monkeypatch, upstream, message: str = "top import partners"):
    install_optional_auth_dependency_fakes()
    from app.api.v1.endpoints import chat as endpoint
    from app.schemas.common import ChatRequest

    async def create_chat(*_args, **_kwargs):
        return FakeChat()

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(endpoint, "create_or_get_chat", create_chat)
    monkeypatch.setattr(endpoint, "touch_chat", noop)
    monkeypatch.setattr(endpoint, "enforce_rate_limit", noop)
    monkeypatch.setattr(endpoint, "add_audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(endpoint, "main_chatbot_client", upstream)
    monkeypatch.setattr(endpoint.settings, "use_standard_chat_stream", False)
    response = await endpoint.stream_chat(ChatRequest(message=message), FakeRequest(), user=FakeUser(), db=FakeDb())
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    parsed = []
    for block in body.decode().strip().split("\n\n"):
        event = next(line[6:].strip() for line in block.splitlines() if line.startswith("event:"))
        data = "\n".join(line[5:].strip() for line in block.splitlines() if line.startswith("data:"))
        parsed.append((event, json.loads(data)))
    return parsed


def test_trade_stream_exposes_only_contract_events_and_normalized_done(monkeypatch):
    upstream = FakeClient(events=[
        ("progress", {"stage": "retrieving"}),
        ("delta", "Cambodia's top import partner is China. "),
        ("done", {
            "intent": "trade_query", "status": "completed", "answer": "Cambodia's top import partner is China.",
            "table": {"rows": [{"partner_country": "China", "value_usd": 12419875213.99}]},
        }),
    ], result={
        "intent": "trade_query", "status": "completed", "answer": "Cambodia's top import partner is China.",
        "table": {"rows": [{"partner_country": "China", "value_usd": 12419875213.99}]},
    })
    events = asyncio.run(stream_events(monkeypatch, upstream))

    assert [event for event, _data in events] == ["start", "delta", "done"]
    assert events[1][1] == {"content": "Cambodia's top import partner is China. "}
    done = events[-1][1]
    assert done["api_version"] == "1.0"
    assert done["service"] == "trade"
    assert [block["type"] for block in done["message"]["content"]] == ["markdown", "table"]
    assert [call[0:2] for call in upstream.calls] == [("POST", "/query/stream")]


def test_trade_stream_uses_authoritative_query_done_after_generic_stream_answer(monkeypatch):
    generic_answer = (
        "SUMMARY OF KEY FINDINGS:\n\n"
        "- The raw trade data provided contains specific figures and metrics.\n\n"
        "DATA VISUALIZATION SUGGESTIONS:\n\n"
        "- Bar charts are recommended."
    )
    authoritative_answer = (
        "Cambodia recorded total imports of $6.17 billion in 2026, "
        "noting that the 2026 data is not complete yet."
    )
    upstream = FakeClient(events=[
        ("delta", "SUMMARY OF"),
        ("delta", " KEY FINDINGS:\n\n- The raw trade data provided contains specific figures and metrics."),
        ("done", {
            "api_version": "1.0",
            "status": "completed",
            "service": "trade",
            "intent": "trade_query",
            "coverage": "unknown",
            "response": {"type": "table", "coverage": "unknown", "content": generic_answer, "limitations": []},
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "markdown", "text": generic_answer},
                    {
                        "type": "table",
                        "columns": [{"key": "period", "label": "period"}],
                        "rows": [{"period": "2026"}],
                    },
                    {
                        "type": "chart",
                        "title": "Trade Volume Ranking",
                        "data": {
                            "chartType": "pie",
                            "data": [{"label": "China", "trade_value_usd": 3282093061.95}],
                        },
                    },
                ],
            },
            "citations": [],
            "suggestions": [],
            "clarifications": [],
            "errors": [],
        }),
    ], result={
        "status": "completed",
        "service": "trade",
        "intent": "trade_query",
        "coverage": "unknown",
        "response": {"type": "table", "coverage": "unknown", "content": authoritative_answer, "limitations": []},
        "message": {
            "role": "assistant",
            "content": [
                {"type": "markdown", "text": authoritative_answer},
                {
                    "type": "table",
                    "columns": [{"key": "period", "label": "period"}],
                    "rows": [{"period": "2026"}],
                },
            ],
        },
        "citations": [],
        "suggestions": [],
        "clarifications": [],
        "errors": [],
    })
    events = asyncio.run(stream_events(monkeypatch, upstream))

    assert [event for event, _data in events] == ["start", "delta", "delta", "done"]
    done = events[-1][1]
    assert done["response"]["content"] == authoritative_answer
    assert done["message"]["content"][0]["text"] == authoritative_answer
    assert "SUMMARY OF KEY FINDINGS" not in done["response"]["content"]
    assert upstream.calls[0][0:2] == ("POST", "/query/stream")
    assert upstream.calls[1][0:2] == ("POST", "/query")


def test_stream_fallback_does_not_fake_deltas_or_blocks(monkeypatch):
    request = httpx.Request("POST", "http://orchestrator/query/stream")
    upstream = FakeClient(
        stream_error=httpx.HTTPStatusError("not found", request=request, response=httpx.Response(404, request=request)),
        result={"intent": "trade_query", "status": "completed", "answer": "Complete trade answer.", "table": {"rows": []}},
    )
    events = asyncio.run(stream_events(monkeypatch, upstream))

    assert [event for event, _data in events] == ["start", "done"]
    assert events[-1][1]["response"]["content"] == "Complete trade answer."


def test_interrupted_live_stream_uses_authoritative_query_done(monkeypatch):
    class InterruptedClient(FakeClient):
        async def stream_chat(self, body):
            yield ChatStreamEvent(type="delta", content="temporary text")
            raise RuntimeError("socket closed")

    upstream = InterruptedClient(result={"intent": "trade_query", "status": "completed", "answer": "Authoritative answer."})
    events = asyncio.run(stream_events(monkeypatch, upstream))

    assert [event for event, _data in events] == ["start", "delta", "done"]
    assert events[-1][1]["response"]["content"] == "Authoritative answer."


def test_general_stream_empty_done_uses_authoritative_query_done(monkeypatch):
    answer = "Hello! I'm here to help you with Cambodia customs and trade questions. How can I assist you today?"
    upstream = FakeClient(events=[
        ("delta", answer),
        ("done", {
            "api_version": "1.0",
            "status": "completed",
            "service": "unknown",
            "intent": "general",
            "response": {"type": "markdown", "coverage": "unknown", "content": "", "limitations": []},
            "message": {"role": "assistant", "content": [{"type": "markdown", "text": ""}]},
            "citations": [],
            "suggestions": [],
            "clarifications": [],
            "errors": [],
        }),
    ], result={
        "status": "completed",
        "service": "unknown",
        "intent": "small_talk",
        "answer": answer,
    })
    events = asyncio.run(stream_events(monkeypatch, upstream))

    assert [event for event, _data in events] == ["start", "delta", "done"]
    done = events[-1][1]
    assert done["status"] == "completed"
    assert done["response"]["content"] == answer
    assert done["message"]["content"][0]["type"] == "markdown"
    assert done["message"]["content"][0]["text"] == answer
    assert upstream.calls[0][0:2] == ("POST", "/query/stream")
    assert upstream.calls[1][0:2] == ("POST", "/query")


def test_general_stream_suggestions_only_done_uses_authoritative_query_done(monkeypatch):
    answer = "A dog is a domesticated mammal."
    upstream = FakeClient(events=[
        ("delta", "DIRECT ANSWER:\nTo clear goods through the General Department of Customs and Excise..."),
        ("done", {
            "api_version": "1.0",
            "status": "completed",
            "service": "general",
            "intent": "general",
            "response": {"type": "markdown", "coverage": "unknown", "content": "", "limitations": []},
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "suggestions",
                        "title": "Suggested follow-ups",
                        "items": [
                            "How do I classify my goods?",
                            "How is customs duty calculated?",
                            "What documents do I need to import?",
                        ],
                    },
                ],
            },
        }),
    ], result={
        "status": "completed",
        "service": "unknown",
        "intent": "small_talk",
        "answer": answer,
        "suggestions": ["What animals are commonly kept as pets?"],
    })
    events = asyncio.run(stream_events(monkeypatch, upstream))

    assert [event for event, _data in events] == ["start", "delta", "done"]
    done = events[-1][1]
    assert done["response"]["content"] == answer
    assert [block["type"] for block in done["message"]["content"]] == ["markdown", "suggestions"]
    assert done["message"]["content"][0]["text"] == answer
    assert upstream.calls[0][0:2] == ("POST", "/query/stream")
    assert upstream.calls[1][0:2] == ("POST", "/query")


def test_calculator_stream_done_uses_authoritative_query_after_generic_fallback(monkeypatch):
    question = "can u calculate tax for 8703.22.00 china cif10500usd acfta dv 0"
    generic_delta = (
        "I can help calculate customs duty. Please provide HS code, origin, CIF value, "
        "and trade agreement details."
    )
    authoritative_response = {
        "status": "completed",
        "service": "calculator",
        "intent": "calculation",
        "answer": "Import tax calculation completed.",
        "calculator_result": {
            "summary": {
                "total_tax": 1470,
                "currency": "USD",
                "phase_gap": 0,
            },
            "product": {
                "hs_code": "8703.22.00",
                "description": "Motor cars and other motor vehicles",
                "origin_country": "China",
                "trade_agreement": "ACFTA",
            },
            "inputs": {
                "declared_value": 0,
                "cif_value": 10500,
                "currency": "USD",
            },
            "tax_breakdown": [
                {"component": "Customs Duty", "rate": "0%", "amount": 0},
                {"component": "VAT", "rate": "10%", "amount": 1050},
                {"component": "Special Tax", "rate": "4%", "amount": 420},
            ],
            "phases": [
                {
                    "title": "Step 1: Customs Duty",
                    "lines": [{"rate": "0%", "amount": "0 USD"}],
                },
                {
                    "title": "Step 2: Taxes",
                    "lines": [{"basis": "CIF value", "amount": "1470 USD"}],
                },
            ],
            "assumptions": [
                "Declared value was provided as 0, so CIF value was used as the taxable base.",
                "Rates are based on the supplied ACFTA preference.",
            ],
        },
        "suggestions": [
            "Calculate another vehicle tax scenario",
            "Compare ACFTA and MFN duty for this HS code",
        ],
    }
    upstream = FakeClient(events=[
        ("delta", generic_delta),
        ("done", {
            "api_version": "1.0",
            "status": "completed",
            "service": "general",
            "intent": "general",
            "response": {"type": "markdown", "coverage": "unknown", "content": generic_delta, "limitations": []},
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "markdown", "text": generic_delta},
                    {
                        "type": "suggestions",
                        "items": [
                            "How do I classify my goods?",
                            "How is customs duty calculated?",
                            "What documents do I need to import?",
                        ],
                    },
                ],
            },
            "suggestions": [
                "How do I classify my goods?",
                "How is customs duty calculated?",
                "What documents do I need to import?",
            ],
        }),
    ], result=authoritative_response)

    events = asyncio.run(stream_events(monkeypatch, upstream, message=question))

    assert [event for event, _data in events] == ["start", "delta", "done"]
    done = events[-1][1]
    assert done["service"] == "calculator"
    assert done["intent"] == "calculation"
    block_types = [block["type"] for block in done["message"]["content"]]
    assert block_types[:5] == ["summary", "key_value", "key_value", "table", "details"]
    assert block_types[-1] == "suggestions"
    titles = [block.get("title") for block in done["message"]["content"]]
    assert "Product Information" in titles
    assert "Input Parameters" in titles
    assert "Calculation Details" in titles
    assert done["suggestions"] == authoritative_response["suggestions"]
    assert "How do I classify my goods?" not in json.dumps(done)
    assert "How is customs duty calculated?" not in json.dumps(done)
    assert "What documents do I need to import?" not in json.dumps(done)
    assert upstream.calls[0][0:2] == ("POST", "/query/stream")
    assert upstream.calls[1][0:2] == ("POST", "/query")
    stream_body = upstream.calls[0][2]["json"]
    query_body = upstream.calls[1][2]["json"]
    assert stream_body["question"] == question
    assert query_body["question"] == question
    assert query_body["session_id"] == stream_body["session_id"]
    assert query_body["chat_id"] == stream_body["chat_id"]
    assert query_body["project_id"] == stream_body["project_id"]


def test_orchestrator_sse_parser_ignores_unknown_events_and_never_turns_json_into_delta():
    assert parse_orchestrator_sse_block('event: progress\ndata: {"stage":"retrieving"}') is not None
    assert parse_orchestrator_sse_block('event: block\ndata: {"type":"table"}') is None
    assert parse_orchestrator_sse_block('event: delta\ndata: {"content":{"type":"table"}}') is None
