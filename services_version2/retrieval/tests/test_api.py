"""
Integration tests for the FastAPI endpoints.

Uses FastAPI's ``TestClient`` with a fully mocked ``RetrievalService``
(no live Qdrant, Redis, or Gemini needed). These tests verify:

- Request / response contracts and status codes.
- Pydantic validation (missing fields, invalid values).
- Error handling at the HTTP layer (backend failures, uninitialised service).
- That ``generate_answer=False`` skips answer generation.
- That vehicle-constraint hard filtering behaves correctly.

Run with::

    pytest tests/test_api.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.api import router
from app.api.endpoints import set_service
from fastapi import FastAPI


# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------


def make_app_with_mock_service(mock_service):
    """
    Create an isolated FastAPI app wired to a mock ``RetrievalService``
    so tests can control every dependency without touching real infra.
    """
    app = FastAPI()
    app.include_router(router)
    set_service(mock_service)
    return app


def make_mock_service(docs=None, health_status="healthy"):
    """
    Build a ``MagicMock`` that quacks like ``RetrievalService``.

    - Forces extractive fallback (no Gemini calls).
    - Returns the given ``docs`` from semantic search.
    - Returns empty prefix-scan results by default.
    - Provides a lightweight health check.
    """
    service = MagicMock()
    # Force extractive (non-Gemini) answer path.
    service.gemini_client = None

    service.config = MagicMock()
    service.config.qdrant_hs_code_collection = "gdce_hs_code"
    service.config.gdce_tariff_search_url = "https://example.gov.kh/tariff"

    # Semantic search returns the provided sample docs (or empty).
    service.orchestrator = MagicMock()
    service.orchestrator.retrieve_semantic = AsyncMock(return_value=docs or [])

    # No structured prefix hits by default → falls back to semantic path.
    service.fetch_hs_documents_by_prefix_async = AsyncMock(return_value=[])
    service._score_hs_candidates_by_query = MagicMock(
        side_effect=lambda query, documents, target_heading: documents
    )

    service.health_check = AsyncMock(return_value={
        "status": health_status,
        "service": "Retrieval Service v2",
        "port": 8003,
        "components": {"vector_store": {"status": "not_checked"}},
    })
    return service


# ---------------------------------------------------------------------------
# Sample documents shared across test cases.
# ---------------------------------------------------------------------------

SAMPLE_DOCS = [
    {
        "id": "1",
        "content": "Motor cars, spark-ignition engine, 1500-3000cc, CBU",
        "score": 0.9,
        "hs_code": "8703.23.10",
        "metadata": {"hs_code": "8703.23.10"},
    },
    {
        "id": "2",
        "content": "Motor cars, diesel engine, 1500-2500cc, CBU",
        "score": 0.7,
        "hs_code": "8703.32.10",
        "metadata": {"hs_code": "8703.32.10"},
    },
]


# =========================================================================
# Test: GET /
# =========================================================================


class TestRootEndpoint:
    """Smoke test for the root / service-identity endpoint."""

    def test_root_returns_service_info(self):
        """Verify the root endpoint returns service name, port, and endpoint map."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["service"] == "Retrieval Service v2 (HS Code Classification)"
        assert body["port"] == 8003
        assert "hs_code_candidates" in body["endpoints"]


# =========================================================================
# Test: GET /health
# =========================================================================


class TestHealthEndpoint:
    """Health-check endpoint behaviour under normal and failure conditions."""

    def test_health_healthy(self):
        """Healthy service returns 200 with status=healthy."""
        service = make_mock_service(health_status="healthy")
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_health_service_exception_returns_unhealthy_not_500(self):
        """
        When the service's health_check raises, the endpoint should catch
        the exception and return 200 with status=unhealthy rather than
        propagating a 500.
        """
        service = make_mock_service()
        service.health_check = AsyncMock(side_effect=RuntimeError("boom"))
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unhealthy"


# =========================================================================
# Test: POST /hs-code-candidates
# =========================================================================


class TestHsCodeCandidatesEndpoint:
    """
    Full integration tests for the primary HS code candidates endpoint.

    Covers: missing query, empty query, valid results, no results,
    generate_answer=False, backend failures (fail-open), top_k validation,
    and hard vehicle-constraint filtering.
    """

    def test_missing_query_returns_422(self):
        """Pydantic rejects requests with no query field."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/hs-code-candidates", json={})
        assert resp.status_code == 422

    def test_empty_query_string_returns_422(self):
        """Pydantic rejects empty query strings (min_length=1)."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/hs-code-candidates", json={"query": ""})
        assert resp.status_code == 422

    def test_valid_query_with_results(self):
        """
        A query with no fuel/body/drive constraints should return both
        sample documents and an extractive ranked answer.
        """
        service = make_mock_service(docs=SAMPLE_DOCS)
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/hs-code-candidates",
            json={"query": "motor car", "generate_answer": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["total_count"] == 2
        assert body["final_answer"] is not None
        assert body["answer_source"] == "extractive_ranked"
        assert body["reference_url"] == "https://example.gov.kh/tariff"

    def test_fuel_constraint_hard_filters_out_non_matching_docs(self):
        """
        A query specifying "diesel" should hard-filter out the
        spark-ignition document, leaving only the diesel match.
        """
        service = make_mock_service(docs=SAMPLE_DOCS)
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/hs-code-candidates", json={"query": "diesel car"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 1
        assert body["documents"][0]["metadata"]["hs_code"] == "8703.32.10"

    def test_valid_query_no_results(self):
        """A query with no matching documents returns 200 with empty results."""
        service = make_mock_service(docs=[])
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/hs-code-candidates",
            json={"query": "totally unmatched gibberish product xzy"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 0
        assert body["documents"] == []

    def test_generate_answer_false_skips_answer(self):
        """When generate_answer=False, final_answer and answer_source are None."""
        service = make_mock_service(docs=SAMPLE_DOCS)
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/hs-code-candidates",
            json={"query": "car", "generate_answer": False},
        )
        assert resp.status_code == 200
        assert resp.json()["final_answer"] is None

    def test_retrieval_backend_failure_degrades_gracefully_not_500(self):
        """
        A failing vector-store call is caught by ``asyncio.gather(..., return_exceptions=True)``
        inside ``_build_hs_candidate_documents``, so the endpoint returns
        200 with an empty result set rather than a 500. This documents the
        intentional fail-open behaviour.
        """
        service = make_mock_service()
        service.orchestrator.retrieve_semantic = AsyncMock(
            side_effect=RuntimeError("qdrant down")
        )
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/hs-code-candidates", json={"query": "car"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_count"] == 0
        assert body["final_answer"] is None

    def test_service_raising_synchronously_returns_500(self):
        """
        A failure OUTSIDE the guarded ``asyncio.gather`` (e.g. in config
        access) should still surface as a 500.
        """
        service = make_mock_service()
        type(service).config = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("config broken"))
        )
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/hs-code-candidates", json={"query": "car"})
        assert resp.status_code == 500

    def test_top_k_validation_rejects_zero(self):
        """Pydantic rejects top_k=0 (field ge=1)."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post(
            "/hs-code-candidates", json={"query": "car", "top_k": 0}
        )
        assert resp.status_code == 422


# =========================================================================
# Test: POST /hs-code-ranked
# =========================================================================


class TestHsCodeRankedEndpoint:
    """Simplified ranked endpoint — contract and validation tests."""

    def test_valid_query(self):
        """A valid query returns 200 with a ranked final_answer."""
        service = make_mock_service(docs=SAMPLE_DOCS)
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/hs-code-ranked", json={"query": "diesel car"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["final_answer"] is not None

    def test_missing_query_returns_422(self):
        """Pydantic rejects requests with no query field."""
        service = make_mock_service()
        app = make_app_with_mock_service(service)
        client = TestClient(app)
        resp = client.post("/hs-code-ranked", json={})
        assert resp.status_code == 422


# =========================================================================
# Test: Service not initialised
# =========================================================================


class TestServiceNotInitialized:
    """
    Verify the behaviour when ``set_service()`` was never called (or was
    called with None), simulating a misconfigured application.
    """

    def test_raises_when_no_service_set(self):
        """
        Any endpoint that depends on ``get_service()`` should return 500
        (not crash the server) when the service singleton is None.
        """
        import app.api.endpoints as ep

        ep._service = None
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 500