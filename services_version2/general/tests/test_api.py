"""
Integration tests for the General Retrieval Service FastAPI endpoints.

Uses FastAPI's ``TestClient`` with a fully mocked ``GeneralRetrievalService``
(no live Qdrant, Redis, or Gemini needed). These tests verify:

- Request / response contracts and status codes.
- Pydantic validation (missing fields, invalid values).
- Error handling at the HTTP layer (backend failures, uninitialised service).
- That ``generate_answer=False`` skips answer generation.
- That trade-data clarification is triggered correctly.

Run with::

    pytest tests/test_api.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.api.endpoints import router, set_service
from fastapi import FastAPI


# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------


def make_app_with_mock_service(mock_service):
    """
    Create an isolated FastAPI app wired to a mock ``GeneralRetrievalService``
    so tests can control every dependency without touching real infra.

    Sets up a mock ``_answer_generator`` AFTER ``set_service()`` so the
    endpoint can generate controlled answers without real Gemini / vLLM calls.
    """
    import app.api.endpoints as ep

    app = FastAPI()
    app.include_router(router)
    set_service(mock_service)

    # Override the real AnswerGenerator with a controlled mock.
    mock_ag = MagicMock()
    mock_ag.generate = AsyncMock(return_value={
        "final_answer": "Here is what I found: test content",
        "answer_source": "extractive_fallback",
    })
    ep._answer_generator = mock_ag

    return app


def make_mock_service(docs=None, status="success", clarification=None):
    """
    Build a ``MagicMock`` that quacks like ``GeneralRetrievalService``.

    - Returns a controlled ``retrieve()`` result.
    - Provides a lightweight health check.
    """
    service = MagicMock()
    service.config = MagicMock()
    service.config.gemini_enabled = False  # force extractive fallback
    service.config.gdce_tariff_search_url = "https://example.gov.kh/tariff"
    service.gemini_client = None

    service.retrieve = AsyncMock(return_value={
        "query": "test query",
        "documents": docs or [],
        "status": status,
        "semantic_count": len(docs or []),
        "structured_count": 0,
        "total_count": len(docs or []),
        "session_id": None,
        "language": "en",
        "api_visibility": {
            "api_called": "/retrieval/retrieve",
            "collection_used": "gdce_docs",
            "processing_path": "semantic+structured",
        },
        "keywords": ["test", "query"],
        "clarification": clarification,
        "missing_parameters": None,
        "error": None,
    })

    service.health_check = AsyncMock(return_value={
        "status": "healthy",
        "service": "General Retrieval Service",
        "port": 8005,
        "components": {
            "vector_store": {"status": "not_checked"},
            "embeddings": {"status": "not_checked"},
            "repository": {"status": "not_checked"},
        },
    })
    return service


SAMPLE_DOCS = [
    {
        "id": "1",
        "content": "Importers must submit a customs declaration form (Form D).",
        "score": 0.92,
        "metadata": {"title": "Import Procedures FAQ"},
    },
    {
        "id": "2",
        "content": "A commercial invoice and packing list are also required.",
        "score": 0.85,
        "metadata": {"title": "Required Documents"},
    },
]


# =========================================================================
# Test: GET /health
# =========================================================================


class TestHealthEndpoint:
    """Health-check endpoint behaviour under normal and failure conditions."""

    def test_health_healthy(self):
        """Healthy service returns 200 with status=healthy."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_service_exception_returns_unhealthy_not_500(self):
        """
        When the service's health_check raises, the endpoint should catch
        the exception and return 200 with status=unhealthy.
        """
        service = make_mock_service()
        service.health_check = AsyncMock(side_effect=RuntimeError("boom"))
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unhealthy"


# =========================================================================
# Test: POST /retrieval/retrieve
# =========================================================================


class TestRetrieveEndpoint:
    """
    Full integration tests for the primary retrieval endpoint.

    Covers: missing query, empty query, valid results, no results,
    generate_answer=False, backend failures, and trade-data clarification.
    """

    def test_missing_query_returns_422(self):
        """Pydantic rejects requests with no query field."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/retrieval/retrieve", json={})
        assert resp.status_code == 422

    def test_empty_query_string_returns_422(self):
        """Pydantic rejects empty query strings (min_length=1)."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/retrieval/retrieve", json={"query": ""})
        assert resp.status_code == 422

    def test_valid_query_with_results(self):
        """A valid query returns 200 with documents and an answer."""
        service = make_mock_service(docs=SAMPLE_DOCS)
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/retrieval/retrieve",
            json={"query": "import documents", "generate_answer": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["total_count"] == 2
        assert body["final_answer"] is not None

    def test_valid_query_no_results(self):
        """A query matching nothing returns 200 with empty results."""
        service = make_mock_service(docs=[])
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/retrieval/retrieve",
            json={"query": "COMPLETELY UNMATCHED GIBBERISH xyz123"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 0
        assert body["documents"] == []

    def test_generate_answer_false_skips_answer(self):
        """When generate_answer=False, final_answer is None."""
        service = make_mock_service(docs=SAMPLE_DOCS)
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/retrieval/retrieve",
            json={"query": "import docs", "generate_answer": False},
        )
        assert resp.status_code == 200
        assert resp.json()["final_answer"] is None

    def test_clarification_required_status(self):
        """
        When the service returns clarification_required, the final_answer
        is the clarification message.
        """
        service = make_mock_service(
            docs=[],
            status="clarification_required",
            clarification="Please provide a time period for trade data queries.",
        )
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/retrieval/retrieve",
            json={
                "query": "import statistics",
                "require_period_for_trade": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "clarification_required"
        assert "time period" in (body.get("final_answer") or "").lower()

    def test_retrieval_backend_failure_degrades_gracefully(self):
        """
        A failing retrieve() call should be caught by the endpoint handler
        and return a 500 — the error is logged but the server stays up.
        """
        service = make_mock_service()
        service.retrieve = AsyncMock(side_effect=RuntimeError("Qdrant down"))
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/retrieval/retrieve", json={"query": "import procedures"}
        )
        assert resp.status_code == 500


# =========================================================================
# Test: GET /
# =========================================================================


class TestRootEndpoint:
    """Smoke test for the root / service-identity endpoint."""

    def test_root_returns_service_info(self):
        """The root endpoint returns service name and port."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert "service" in body
        assert body["port"] == 8005


# =========================================================================
# Test: Service not initialised
# =========================================================================


class TestServiceNotInitialized:
    """
    Verify behaviour when ``set_service()`` was never called.
    """

    def test_raises_when_no_service_set(self):
        """Endpoints return 500 when the service singleton is None."""
        import app.api.endpoints as ep

        ep._service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 500
