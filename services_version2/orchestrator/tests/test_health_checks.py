"""
Health Checks Tests
Tests the health check service implementation
"""

import pytest
import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.health_checks import (
    ServiceHealthStatus,
    SystemReadiness,
    ServiceHealth,
    SystemHealth,
    HealthCheckService,
    get_health_check_service,
    initialize_health_check_service,
)


class TestServiceHealthStatus:
    """Tests for ServiceHealthStatus enum."""
    
    def test_health_status_values(self):
        """Test health status enum values."""
        assert ServiceHealthStatus.UP.value == "up"
        assert ServiceHealthStatus.DOWN.value == "down"
        assert ServiceHealthStatus.DEGRADED.value == "degraded"
        assert ServiceHealthStatus.UNKNOWN.value == "unknown"


class TestSystemReadiness:
    """Tests for SystemReadiness enum."""
    
    def test_readiness_values(self):
        """Test readiness enum values."""
        assert SystemReadiness.READY.value == "ready"
        assert SystemReadiness.NOT_READY.value == "not_ready"
        assert SystemReadiness.DEGRADED.value == "degraded"


class TestServiceHealth:
    """Tests for ServiceHealth data class."""
    
    def test_service_health_creation(self):
        """Test creating service health object."""
        health = ServiceHealth(
            name="test_service",
            status=ServiceHealthStatus.UP,
            response_time_ms=50.0,
            circuit_state="closed"
        )
        
        assert health.name == "test_service"
        assert health.status == ServiceHealthStatus.UP
        assert health.response_time_ms == 50.0
        assert health.circuit_state == "closed"
        assert health.consecutive_failures == 0
        assert health.consecutive_successes == 0
    
    def test_service_health_to_dict(self):
        """Test converting service health to dictionary."""
        health = ServiceHealth(
            name="test_service",
            status=ServiceHealthStatus.UP,
            response_time_ms=50.0
        )
        
        health_dict = health.to_dict()
        
        assert health_dict["name"] == "test_service"
        assert health_dict["status"] == "up"
        assert health_dict["response_time_ms"] == 50.0
        assert health_dict["consecutive_failures"] == 0


class TestHealthCheckServiceConfig:
    """Tests for HealthCheckService configuration."""
    
    def test_default_config(self):
        """Test default health check configuration."""
        service = HealthCheckService()
        
        assert service.check_timeout_sec == 5
        assert service.failure_threshold == 3
        assert service.degraded_response_time_ms == 1000.0
    
    def test_custom_config(self):
        """Test custom health check configuration."""
        service = HealthCheckService(
            check_timeout_sec=10,
            failure_threshold=5,
            degraded_response_time_ms=500.0
        )
        
        assert service.check_timeout_sec == 10
        assert service.failure_threshold == 5
        assert service.degraded_response_time_ms == 500.0


@pytest.mark.asyncio
class TestHealthCheckServiceBehavior:
    """Tests for health check service behavior."""
    
    async def test_check_service_health_up(self):
        """Test service health check when service is up."""
        service = HealthCheckService()
        
        # Mock client with health method
        mock_client = Mock()
        mock_response = {"status": "ok"}
        
        async def mock_health():
            return mock_response
        
        mock_client.health = mock_health
        
        health = await service.check_service_health("test_service", mock_client)
        
        assert health.name == "test_service"
        assert health.status == ServiceHealthStatus.UP
        assert health.response_time_ms is not None
        assert health.response_time_ms >= 0
    
    async def test_check_service_health_timeout(self):
        """Test service health check when service times out."""
        service = HealthCheckService(check_timeout_sec=1)
        
        # Mock client that times out
        mock_client = Mock()
        
        async def timeout_health():
            await asyncio.sleep(2)  # Sleep longer than timeout
            return {"status": "ok"}
        
        mock_client.health = timeout_health
        
        health = await service.check_service_health("test_service", mock_client)
        
        assert health.name == "test_service"
        assert health.status == ServiceHealthStatus.DOWN
        assert "timeout" in health.error_message.lower()
        assert health.consecutive_failures == 1
    
    async def test_check_service_health_error(self):
        """Test service health check when service throws error."""
        service = HealthCheckService()
        
        # Mock client that raises error
        mock_client = Mock()
        
        async def error_health():
            raise Exception("Connection refused")
        
        mock_client.health = error_health
        
        health = await service.check_service_health("test_service", mock_client)
        
        assert health.name == "test_service"
        assert health.status == ServiceHealthStatus.DOWN
        assert "Connection refused" in health.error_message
        assert health.consecutive_failures == 1
    
    async def test_check_service_health_degraded(self):
        """Test service health check when service is degraded (slow)."""
        service = HealthCheckService(
            degraded_response_time_ms=100.0  # Very low threshold for testing
        )
        
        # Mock client that returns slowly
        async def slow_health():
            await asyncio.sleep(0.2)  # 200ms delay
            return {"status": "ok"}
        
        mock_client = Mock()
        mock_client.health = slow_health
        
        health = await service.check_service_health("test_service", mock_client)
        
        assert health.name == "test_service"
        assert health.status == ServiceHealthStatus.DEGRADED
        assert health.response_time_ms > 100.0
    
    async def test_check_service_with_circuit_breaker(self):
        """Test health check with circuit breaker status."""
        service = HealthCheckService()
        
        # Mock client with circuit breaker
        mock_client = Mock()
        
        async def mock_health():
            return {"status": "ok"}
        
        mock_client.health = mock_health
        mock_client.get_circuit_breaker_status.return_value = {
            "state": "closed",
            "failure_count": 0
        }
        
        health = await service.check_service_health("test_service", mock_client)
        
        assert health.status == ServiceHealthStatus.UP
        assert health.circuit_state == "closed"
        assert health.metadata["circuit_breaker"]["state"] == "closed"
    
    async def test_consecutive_failure_tracking(self):
        """Test tracking consecutive failures."""
        service = HealthCheckService()
        
        async def error_health():
            raise Exception("Error")
        
        mock_client = Mock()
        mock_client.health = error_health
        
        # Multiple failures
        for i in range(3):
            health = await service.check_service_health("test_service", mock_client)
            assert health.consecutive_failures == i + 1
            assert health.consecutive_successes == 0
    
    async def test_consecutive_success_tracking(self):
        """Test tracking consecutive successes."""
        service = HealthCheckService()
        
        async def mock_health():
            return {"status": "ok"}
        
        mock_client = Mock()
        mock_client.health = mock_health
        
        # Multiple successes
        for i in range(3):
            health = await service.check_service_health("test_service", mock_client)
            assert health.consecutive_failures == 0
            assert health.consecutive_successes == i + 1
    
    async def test_failure_count_reset_on_success(self):
        """Test that failure count resets on success."""
        service = HealthCheckService()
        
        async def error_health():
            raise Exception("Error")
        
        mock_client = Mock()
        mock_client.health = error_health
        
        # First fail
        health1 = await service.check_service_health("test_service", mock_client)
        assert health1.consecutive_failures == 1
        
        # Then succeed
        async def mock_health():
            return {"status": "ok"}
        
        mock_client.health = mock_health
        health2 = await service.check_service_health("test_service", mock_client)
        assert health2.consecutive_failures == 0
        assert health2.consecutive_successes == 1


@pytest.mark.asyncio
class TestHealthCheckServiceMultiple:
    """Tests for checking multiple services."""
    
    async def test_check_all_services_all_up(self):
        """Test checking all services when all are up."""
        service = HealthCheckService()
        
        async def mock_health():
            return {"status": "ok"}
        
        # Mock multiple services
        services = {}
        for svc_name in ["retrieval", "calculator", "trade_data"]:
            mock_client = Mock()
            mock_client.health = mock_health
            services[svc_name] = mock_client
        
        # Check all
        system_health = await service.check_all_services(services)
        
        assert system_health.overall_status == ServiceHealthStatus.UP
        assert system_health.readiness == SystemReadiness.READY
        assert len(system_health.services) == 3
        assert all(h.status == ServiceHealthStatus.UP for h in system_health.services.values())
    
    async def test_check_all_services_one_down(self):
        """Test checking all services when one is down."""
        service = HealthCheckService()
        
        async def ok_health():
            return {"status": "ok"}
        
        async def error_health():
            raise Exception("Down")
        
        # Mock multiple services
        services = {}
        
        retrieval_client = Mock()
        retrieval_client.health = ok_health
        services["retrieval"] = retrieval_client
        
        calculator_client = Mock()
        calculator_client.health = error_health
        services["calculator"] = calculator_client
        
        tradedata_client = Mock()
        tradedata_client.health = ok_health
        services["trade_data"] = tradedata_client
        
        # Check all
        system_health = await service.check_all_services(services)
        
        assert system_health.overall_status == ServiceHealthStatus.DOWN
        assert system_health.readiness == SystemReadiness.NOT_READY
        assert system_health.services["calculator"].status == ServiceHealthStatus.DOWN
    
    async def test_check_all_services_degraded(self):
        """Test checking all services when some are degraded."""
        service = HealthCheckService(degraded_response_time_ms=100.0)
        
        async def ok_health():
            return {"status": "ok"}
        
        async def slow_health():
            await asyncio.sleep(0.2)
            return {"status": "ok"}
        
        # Mock services
        retrieval_client = Mock()
        retrieval_client.health = ok_health
        
        calculator_client = Mock()
        calculator_client.health = slow_health
        
        services = {
            "retrieval": retrieval_client,
            "calculator": calculator_client,
        }
        
        # Check all
        system_health = await service.check_all_services(services)
        
        assert system_health.overall_status == ServiceHealthStatus.DEGRADED
        assert system_health.readiness == SystemReadiness.DEGRADED
        assert system_health.services["calculator"].status == ServiceHealthStatus.DEGRADED
    
    async def test_system_health_metadata(self):
        """Test system health includes proper metadata."""
        service = HealthCheckService()
        
        async def ok_health():
            return {"status": "ok"}
        
        async def error_health():
            raise Exception("Error")
        
        retrieval_client = Mock()
        retrieval_client.health = ok_health
        
        calculator_client = Mock()
        calculator_client.health = error_health
        
        services = {
            "retrieval": retrieval_client,
            "calculator": calculator_client,
        }
        
        system_health = await service.check_all_services(services)
        
        metadata = system_health.metadata
        assert metadata["services_checked"] == 2
        assert metadata["healthy_services"] == 1
        assert metadata["down_services"] == 1
        assert metadata["check_count"] >= 1


class TestHealthCheckServiceStatus:
    """Tests for getting health check status."""
    
    def test_get_last_health_empty(self):
        """Test getting last health when none exists."""
        service = HealthCheckService()
        assert service.get_last_health() is None
    
    def test_get_service_health(self):
        """Test getting specific service health."""
        service = HealthCheckService()
        
        health = ServiceHealth(
            name="test_service",
            status=ServiceHealthStatus.UP
        )
        
        service.service_healths["test_service"] = health
        
        retrieved = service.get_service_health("test_service")
        assert retrieved.name == "test_service"
        assert retrieved.status == ServiceHealthStatus.UP
    
    def test_get_all_services_health(self):
        """Test getting all services health."""
        service = HealthCheckService()
        
        health1 = ServiceHealth(name="service1", status=ServiceHealthStatus.UP)
        health2 = ServiceHealth(name="service2", status=ServiceHealthStatus.DOWN)
        
        service.service_healths["service1"] = health1
        service.service_healths["service2"] = health2
        
        all_health = service.get_all_services_health()
        
        assert len(all_health) == 2
        assert all_health["service1"].status == ServiceHealthStatus.UP
        assert all_health["service2"].status == ServiceHealthStatus.DOWN
    
    def test_get_error_history(self):
        """Test getting error history."""
        service = HealthCheckService()
        
        service._record_error("service1", "Error 1")
        service._record_error("service2", "Error 2")
        service._record_error("service1", "Error 3")
        
        history = service.get_error_history()
        
        assert len(history) == 3
        assert history[0]["service"] == "service1"
        assert history[2]["service"] == "service1"
    
    def test_get_health_metrics(self):
        """Test getting health metrics."""
        service = HealthCheckService()
        
        health = ServiceHealth(name="test", status=ServiceHealthStatus.UP)
        service.service_healths["test"] = health
        service.check_count = 5
        
        metrics = service.get_health_metrics()
        
        assert metrics["check_count"] == 5
        assert metrics["services_count"] == 1


class TestGlobalHealthCheckService:
    """Tests for global health check service instance."""
    
    def test_get_health_check_service(self):
        """Test getting global health check service."""
        service1 = get_health_check_service()
        service2 = get_health_check_service()
        
        # Should return same instance
        assert service1 is service2
    
    def test_initialize_health_check_service(self):
        """Test initializing health check service with custom config."""
        service = initialize_health_check_service(
            check_timeout_sec=10,
            failure_threshold=5,
            degraded_response_time_ms=500.0
        )
        
        assert service.check_timeout_sec == 10
        assert service.failure_threshold == 5
        assert service.degraded_response_time_ms == 500.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
