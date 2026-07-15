from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.endpoints.chat import (
    adapt_orchestrator_sse_block,
    orchestrator_query_payload,
    orchestrator_stream_payload,
    upstream_payload,
)
from app.main import app
from app.schemas.common import ChatRequest


def test_required_route_surface_exists():
    routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
    required = {
        ("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"), ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/auth/me"), ("POST", "/api/v1/chat/send"),
        ("POST", "/api/v1/chat/stream"), ("GET", "/api/v1/chat/history"),
        ("GET", "/api/v1/jobs/{job_id}"), ("GET", "/api/v1/jobs/{job_id}/result"),
        ("GET", "/api/v1/services"), ("GET", "/api/v1/health"),
    }
    assert required <= routes


def test_upstream_identity_and_existing_project_come_from_gateway():
    project_id, chat_id, user_id = uuid4(), uuid4(), uuid4()
    payload = ChatRequest(message="hello")
    forwarded = upstream_payload(
        payload,
        SimpleNamespace(id=chat_id, project_id=project_id),
        SimpleNamespace(id=user_id, role="user"),
        "request-id",
    )
    assert forwarded["chat_id"] == str(chat_id)
    assert forwarded["project_id"] == str(project_id)
    assert forwarded["user_id"] == str(user_id)


def test_orchestrator_stream_payload_uses_message_and_chat_session():
    chat_id = uuid4()
    payload = ChatRequest(message="What is the HS code for rice?")

    expected = {
        "question": "What is the HS code for rice?",
        "session_id": str(chat_id),
    }
    assert orchestrator_query_payload(payload, SimpleNamespace(id=chat_id)) == expected
    assert orchestrator_stream_payload(payload, SimpleNamespace(id=chat_id)) == expected


def test_orchestrator_stream_chunk_is_adapted_to_frontend_token_event():
    adapted = adapt_orchestrator_sse_block(
        'data: {"chunk": "hello"}',
        SimpleNamespace(id=uuid4(), project_id=None),
    ).decode()

    assert adapted == 'event: token\ndata: {"content": "hello"}\n\n'


def test_orchestrator_stream_done_payload_is_normalized_when_complete():
    chat_id = uuid4()
    adapted = adapt_orchestrator_sse_block(
        'event: done\ndata: {"request_id": "req-1", "answer": "hello", "intent": "general", "status": "success"}',
        SimpleNamespace(id=chat_id, project_id=None),
    ).decode()

    assert adapted.startswith("event: done\n")
    assert '"request_id": "req-1"' in adapted
    assert '"session_id": "' + str(chat_id) + '"' in adapted
    assert '"type": "markdown"' in adapted
    assert '"text": "hello"' in adapted
