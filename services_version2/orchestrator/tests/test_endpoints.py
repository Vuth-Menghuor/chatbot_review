"""
Tests for API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from ..app import app


@pytest.fixture
def client():
    """Provide test client."""
    return TestClient(app)


class TestQueryEndpoint:
    """Test /query endpoint."""
    
    def test_query_request(self, client):
        """Test basic query request."""
        response = client.post("/query", json={
            "question": "What is an HS code?"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["question"] == "What is an HS code?"
        assert "status" in data
    
    def test_query_with_session(self, client):
        """Test query with session ID."""
        response = client.post("/query", json={
            "question": "What is VAT?",
            "session_id": "session_123"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["question"] == "What is VAT?"
    
    def test_invalid_question_empty(self, client):
        """Test query with empty question."""
        response = client.post("/query", json={
            "question": ""
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_invalid_question_too_long(self, client):
        """Test query with question exceeding max length."""
        long_question = "x" * 2001
        response = client.post("/query", json={
            "question": long_question
        })
        
        assert response.status_code == 422  # Validation error
    
    def test_invalid_question_too_short(self, client):
        """Test query with question too short."""
        response = client.post("/query", json={
            "question": "a"
        })
        
        assert response.status_code == 422  # Validation error


class TestHealthEndpoint:
    """Test /health endpoint."""
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "services" in data
    
    def test_health_status_values(self, client):
        """Test health status has valid values."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]


class TestStatusEndpoint:
    """Test /status endpoint."""
    
    def test_status_endpoint(self, client):
        """Test status endpoint."""
        response = client.get("/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "orchestrator_v2"
        assert "version" in data
        assert "status" in data


class TestInfoEndpoint:
    """Test /info endpoint."""
    
    def test_info_endpoint(self, client):
        """Test info endpoint."""
        response = client.get("/info")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "description" in data
        assert "capabilities" in data
        assert isinstance(data["capabilities"], list)


class TestExplainEndpoint:
    """Test /query/explain endpoint."""
    
    def test_explain_query(self, client):
        """Test query explanation endpoint."""
        response = client.post("/query/explain", json={
            "question": "What is HS code?"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "question" in data
        assert "intent" in data
        assert "routing" in data
        assert "sequence" in data["routing"]
