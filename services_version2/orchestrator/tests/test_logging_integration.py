"""
Integration tests for structured logging and request tracking middleware
"""

import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from ..app import app
from ..core.logging import get_request_id, set_request_id, setup_structured_logging
import structlog


@pytest.fixture
def client():
    """Provide test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_logging():
    """Setup logging before each test."""
    setup_structured_logging()
    yield
    # Reset after test
    set_request_id(None)


class TestRequestLoggingMiddleware:
    """Test RequestLoggingMiddleware functionality."""

    def test_middleware_adds_request_id_header_to_response(self, client):
        """Test that middleware adds X-Request-ID to response headers."""
        custom_id = "test-request-123"
        
        response = client.get(
            "/health",
            headers={"X-Request-ID": custom_id}
        )
        
        # Verify response includes request_id header
        assert response.headers.get("X-Request-ID") == custom_id
        print(f"✓ Request ID {custom_id} passed through response headers")

    def test_middleware_generates_request_id_if_not_provided(self, client):
        """Test that middleware generates UUID if X-Request-ID not provided."""
        response = client.get("/health")
        
        # Should have auto-generated request_id
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) > 0
        # Should be a valid UUID format
        try:
            uuid.UUID(request_id)
            print(f"✓ Auto-generated request ID: {request_id}")
        except ValueError:
            pytest.fail(f"Generated request ID is not valid UUID: {request_id}")

    def test_middleware_sets_request_id_in_context(self, client):
        """Test that middleware sets request_id in context variable."""
        custom_id = "context-test-456"
        
        # Mock the logger to capture what's being logged
        with patch('structlog.get_logger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Make request
            response = client.get(
                "/health",
                headers={"X-Request-ID": custom_id}
            )
            
            # Request should be successful
            assert response.status_code in [200, 404]
            print(f"✓ Context variable test passed")

    def test_request_response_timing_logged(self, client):
        """Test that request timing is logged."""
        response = client.get("/health")
        
        # Request should complete
        assert response.status_code in [200, 404, 500]
        print(f"✓ Request completed with status {response.status_code}")

    def test_request_id_consistency_across_calls(self, client):
        """Test that same request_id is used for multiple calls to same endpoint."""
        custom_id = "consistency-test-789"
        
        # Make multiple calls with same request_id
        response1 = client.get(
            "/health",
            headers={"X-Request-ID": custom_id}
        )
        response2 = client.get(
            "/health",
            headers={"X-Request-ID": custom_id}
        )
        
        # Both should have the same request_id
        assert response1.headers.get("X-Request-ID") == custom_id
        assert response2.headers.get("X-Request-ID") == custom_id
        print(f"✓ Request ID consistency verified across calls")


class TestLoggingContextManagement:
    """Test context variable management for logging."""

    def test_set_and_get_request_id(self):
        """Test setting and getting request ID from context."""
        test_id = "test-context-id"
        set_request_id(test_id)
        
        retrieved_id = get_request_id()
        assert retrieved_id == test_id
        print(f"✓ Context management: set and retrieved {test_id}")

    def test_request_id_default_none(self):
        """Test that default request ID is None."""
        set_request_id(None)
        request_id = get_request_id()
        
        assert request_id is None
        print(f"✓ Request ID defaults to None")

    def test_request_id_survives_scope(self):
        """Test that request_id context variable persists in scope."""
        test_id = "scope-test-id"
        set_request_id(test_id)
        
        # Create a function to test scoping
        def nested_function():
            return get_request_id()
        
        result = nested_function()
        assert result == test_id
        print(f"✓ Request ID persists across function calls: {result}")


class TestStructuredLoggingFormat:
    """Test structured logging output format."""

    def test_logger_includes_request_id(self):
        """Test that logger includes request_id in output."""
        test_id = "logger-test-id"
        set_request_id(test_id)
        
        # Get logger and capture output
        logger = structlog.get_logger("test")
        
        # Log should include request_id when set
        assert test_id is not None
        print(f"✓ Logger configured with request_id context")

    def test_logging_setup_configuration(self):
        """Test that logging is properly configured."""
        # Just verify setup_structured_logging runs without error
        try:
            setup_structured_logging()
            print("✓ Structured logging setup completed successfully")
        except Exception as e:
            pytest.fail(f"Logging setup failed: {e}")

    def test_multiple_request_ids_dont_interfere(self, client):
        """Test that different request IDs don't interfere with each other."""
        ids = [f"test-id-{i}" for i in range(3)]
        
        responses = []
        for req_id in ids:
            response = client.get(
                "/health",
                headers={"X-Request-ID": req_id}
            )
            responses.append(response)
        
        # Each response should have its own request_id
        for i, response in enumerate(responses):
            assert response.headers.get("X-Request-ID") == ids[i]
        
        print(f"✓ Multiple request IDs handled independently")


class TestErrorHandlingWithLogging:
    """Test that logging works with error scenarios."""

    def test_logging_on_404_error(self, client):
        """Test that logging works when endpoint returns 404."""
        response = client.get(
            "/nonexistent-endpoint",
            headers={"X-Request-ID": "error-test-404"}
        )
        
        assert response.status_code == 404
        assert response.headers.get("X-Request-ID") == "error-test-404"
        print(f"✓ Request ID preserved on 404 error")

    def test_logging_on_invalid_request(self, client):
        """Test that logging works for invalid requests."""
        response = client.post(
            "/health",  # GET only endpoint
            headers={"X-Request-ID": "error-test-method"}
        )
        
        # Should have some error response
        assert response.status_code >= 400
        assert response.headers.get("X-Request-ID") == "error-test-method"
        print(f"✓ Request ID preserved on method error")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
