from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.endpoints.chat import upstream_payload
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
