"""
Tests for API Endpoints
"""

import pytest
from httpx import AsyncClient, ASGITransport
from services_version2.retrieval.app import app
from services_version2.retrieval.api.endpoints import set_service


@pytest.fixture(autouse=True)
async def setup_service(retrieval_service):
    """Setup service in endpoints for each test."""
    set_service(retrieval_service)


@pytest.fixture
async def client():
    """Create AsyncClient with proper ASGI transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
class TestRetrieveEndpoint:
    """Test /v1/retrieval/retrieve endpoint."""
    
    async def test_retrieve_success(self, client):
        """Test successful retrieve endpoint."""
        response = await client.post(
            "/v1/retrieval/retrieve",
            json={
                "query": "HS code for cotton",
                "top_k": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert "status" in data
        assert "documents" in data
    
    async def test_retrieve_with_session_id(self, client):
        """Test retrieve endpoint with session ID."""
        session_id = "test-session-123"
        response = await client.post(
            "/v1/retrieval/retrieve",
            json={
                "query": "test query",
                "session_id": session_id
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
    
    async def test_retrieve_custom_top_k(self, client):
        """Test retrieve endpoint with custom top_k."""
        response = await client.post(
            "/v1/retrieval/retrieve",
            json={
                "query": "test",
                "top_k": 5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) <= 5
    
    async def test_retrieve_invalid_query(self, client):
        """Test retrieve with empty query."""
        response = await client.post(
            "/v1/retrieval/retrieve",
            json={"query": ""}
        )
        
        # Should still return 200, but with invalid_query status
        if response.status_code == 200:
            data = response.json()
            assert data["status"] in ["invalid_query", "error"]
    
    async def test_retrieve_missing_query(self, client):
        """Test retrieve without query parameter."""
        response = await client.post(
            "/v1/retrieval/retrieve",
            json={}
        )
        
        # Should fail validation
        assert response.status_code >= 400
    
    async def test_retrieve_too_large_top_k(self, client):
        """Test retrieve with top_k exceeding max."""
        response = await client.post(
            "/v1/retrieval/retrieve",
            json={
                "query": "test",
                "top_k": 1000
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        # Should be capped to max
        assert len(data["documents"]) <= 100


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Test /v1/health endpoint."""
    
    async def test_health_check_success(self, client):
        """Test health check endpoint."""
        response = await client.get("/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data
    
    async def test_health_status_values(self, client):
        """Test health endpoint returns valid status values."""
        response = await client.get("/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
    
    async def test_health_check_components(self, client):
        """Test health endpoint includes component details."""
        response = await client.get("/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        # Should have at least some components
        assert isinstance(data["components"], dict)


@pytest.mark.asyncio
class TestEndpointIntegration:
    """Integration tests for API endpoints."""
    
    async def test_retrieve_then_health(self, client):
        """Test sequence of retrieval and health check."""
        # First, retrieve
        response1 = await client.post(
            "/v1/retrieval/retrieve",
            json={"query": "test"}
        )
        assert response1.status_code == 200
        
        # Then, health check
        response2 = await client.get("/v1/health")
        assert response2.status_code == 200
    
    async def test_multiple_retrieve_requests(self, client):
        """Test multiple retrieve requests."""
        for i in range(3):
            response = await client.post(
                "/v1/retrieval/retrieve",
                json={"query": f"Query {i}"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["query"] == f"Query {i}"
