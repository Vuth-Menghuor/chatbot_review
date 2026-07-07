"""
Health Check Infrastructure
Manages service health monitoring and circuit breaker status
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class ServiceHealthStatus(Enum):
    """Service health status."""
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class SystemReadiness(Enum):
    """System readiness status."""
    READY = "ready"
    NOT_READY = "not_ready"
    DEGRADED = "degraded"


@dataclass
class ServiceHealth:
    """Service health information."""
    name: str
    status: ServiceHealthStatus
    response_time_ms: Optional[float] = None
    circuit_state: Optional[str] = None
    error_message: Optional[str] = None
    last_check_time: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "response_time_ms": self.response_time_ms,
            "circuit_state": self.circuit_state,
            "error": self.error_message,
            "last_check": self.last_check_time.isoformat() if self.last_check_time else None,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "metadata": self.metadata
        }


@dataclass
class SystemHealth:
    """Overall system health information."""
    timestamp: datetime
    overall_status: ServiceHealthStatus
    readiness: SystemReadiness
    services: Dict[str, ServiceHealth]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "status": self.overall_status.value,
            "readiness": self.readiness.value,
            "services": {name: health.to_dict() for name, health in self.services.items()},
            "metadata": self.metadata
        }


class HealthCheckService:
    """
    Service health monitoring and checking.
    
    Monitors:
    - Backend service availability (retrieval, calculator, trade_data)
    - Circuit breaker states
    - Response times
    - Consecutive failures/successes
    """
    
    def __init__(
        self,
        check_timeout_sec: int = 5,
        failure_threshold: int = 3,
        degraded_response_time_ms: float = 1000.0
    ):
        """
        Initialize health check service.
        
        Args:
            check_timeout_sec: Timeout for individual health checks (default: 5)
            failure_threshold: Consecutive failures before marking down (default: 3)
            degraded_response_time_ms: Response time threshold for degraded status (default: 1000ms)
        """
        self.check_timeout_sec = check_timeout_sec
        self.failure_threshold = failure_threshold
        self.degraded_response_time_ms = degraded_response_time_ms
        
        self.service_healths: Dict[str, ServiceHealth] = {}
        self.last_system_health: Optional[SystemHealth] = None
        self.last_check_time: Optional[datetime] = None
        self.check_count: int = 0
        self.error_history: List[Dict[str, Any]] = []
        self.max_error_history: int = 100
    
    async def check_service_health(self, service_name: str, client) -> ServiceHealth:
        """
        Check health of a service.
        
        Args:
            service_name: Name of service (retrieval, calculator, trade_data)
            client: Service client with health() method
            
        Returns:
            ServiceHealth with current status
        """
        health = ServiceHealth(
            name=service_name,
            status=ServiceHealthStatus.UNKNOWN,
            last_check_time=datetime.now()
        )
        
        try:
            # Measure response time
            start_time = time.time()
            
            try:
                # Call health endpoint with timeout
                response = await asyncio.wait_for(
                    client.health(),
                    timeout=self.check_timeout_sec
                )
                
                elapsed_ms = (time.time() - start_time) * 1000
                health.response_time_ms = elapsed_ms
                
                # Determine status based on response time
                if elapsed_ms > self.degraded_response_time_ms:
                    health.status = ServiceHealthStatus.DEGRADED
                else:
                    health.status = ServiceHealthStatus.UP
                
                # Extract circuit breaker state if available
                if hasattr(client, 'get_circuit_breaker_status'):
                    cb_status = client.get_circuit_breaker_status()
                    health.circuit_state = cb_status.get('state', 'unknown')
                    health.metadata['circuit_breaker'] = cb_status
                
                # Reset consecutive failures on success
                if health.status == ServiceHealthStatus.UP:
                    health.consecutive_failures = 0
                    health.consecutive_successes += 1
                
                logger.debug(
                    f"[HealthCheck] {service_name}: {health.status.value} "
                    f"({elapsed_ms:.1f}ms)"
                )
                
            except asyncio.TimeoutError:
                health.status = ServiceHealthStatus.DOWN
                health.error_message = f"Health check timeout after {self.check_timeout_sec}s"
                health.consecutive_failures += 1
                health.consecutive_successes = 0
                
                logger.warning(
                    f"[HealthCheck] {service_name}: TIMEOUT after {self.check_timeout_sec}s"
                )
        
        except Exception as e:
            health.status = ServiceHealthStatus.DOWN
            health.error_message = str(e)
            health.consecutive_failures += 1
            health.consecutive_successes = 0
            
            # Extract circuit breaker state even on error
            if hasattr(client, 'get_circuit_breaker_status'):
                try:
                    cb_status = client.get_circuit_breaker_status()
                    health.circuit_state = cb_status.get('state', 'unknown')
                    health.metadata['circuit_breaker'] = cb_status
                except:
                    pass
            
            logger.error(
                f"[HealthCheck] {service_name}: ERROR - {type(e).__name__}: {e}"
            )
            
            # Record error in history
            self._record_error(service_name, str(e))
        
        # Update service health record
        if service_name in self.service_healths:
            previous = self.service_healths[service_name]
            # Increment consecutive counts if status didn't change
            if health.status == previous.status and health.status != ServiceHealthStatus.UP:
                health.consecutive_failures = previous.consecutive_failures + 1
            elif health.status == previous.status and health.status == ServiceHealthStatus.UP:
                health.consecutive_successes = previous.consecutive_successes + 1
        
        self.service_healths[service_name] = health
        return health
    
    def _record_error(self, service_name: str, error_message: str):
        """Record error in history for debugging."""
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "service": service_name,
            "error": error_message
        }
        
        self.error_history.append(error_entry)
        
        # Keep only recent errors
        if len(self.error_history) > self.max_error_history:
            self.error_history = self.error_history[-self.max_error_history:]
    
    async def check_all_services(self, service_clients: Dict[str, Any]) -> SystemHealth:
        """
        Check health of all services.
        
        Args:
            service_clients: Dictionary of service name -> client
            
        Returns:
            SystemHealth with aggregate status
        """
        self.check_count += 1
        self.last_check_time = datetime.now()
        
        # Check each service concurrently
        check_tasks = [
            self.check_service_health(name, client)
            for name, client in service_clients.items()
        ]
        
        health_results = await asyncio.gather(*check_tasks, return_exceptions=False)
        
        # Build system health
        system_health = SystemHealth(
            timestamp=datetime.now(),
            overall_status=self._compute_overall_status(),
            readiness=self._compute_readiness(),
            services={h.name: h for h in health_results}
        )
        
        # Add metadata
        system_health.metadata = {
            "check_count": self.check_count,
            "services_checked": len(service_clients),
            "healthy_services": sum(
                1 for h in health_results if h.status == ServiceHealthStatus.UP
            ),
            "degraded_services": sum(
                1 for h in health_results if h.status == ServiceHealthStatus.DEGRADED
            ),
            "down_services": sum(
                1 for h in health_results if h.status == ServiceHealthStatus.DOWN
            ),
            "recent_errors": len(self.error_history)
        }
        
        self.last_system_health = system_health
        
        logger.info(
            f"[HealthCheck] Full system check: "
            f"UP={system_health.metadata['healthy_services']}, "
            f"DEGRADED={system_health.metadata['degraded_services']}, "
            f"DOWN={system_health.metadata['down_services']}"
        )
        
        return system_health
    
    def _compute_overall_status(self) -> ServiceHealthStatus:
        """Compute overall system status."""
        if not self.service_healths:
            return ServiceHealthStatus.UNKNOWN
        
        # If any service is down, system is down
        if any(h.status == ServiceHealthStatus.DOWN for h in self.service_healths.values()):
            return ServiceHealthStatus.DOWN
        
        # If any service is degraded, system is degraded
        if any(h.status == ServiceHealthStatus.DEGRADED for h in self.service_healths.values()):
            return ServiceHealthStatus.DEGRADED
        
        # If all services are up, system is up
        if all(h.status == ServiceHealthStatus.UP for h in self.service_healths.values()):
            return ServiceHealthStatus.UP
        
        # Otherwise degraded
        return ServiceHealthStatus.DEGRADED
    
    def _compute_readiness(self) -> SystemReadiness:
        """Compute system readiness for traffic."""
        if not self.service_healths:
            return SystemReadiness.NOT_READY
        
        # All critical services must be up
        down_services = [h for h in self.service_healths.values() if h.status == ServiceHealthStatus.DOWN]
        if down_services:
            return SystemReadiness.NOT_READY
        
        # If some services degraded, system is degraded but ready
        degraded_services = [h for h in self.service_healths.values() if h.status == ServiceHealthStatus.DEGRADED]
        if degraded_services:
            return SystemReadiness.DEGRADED
        
        # All services up
        return SystemReadiness.READY
    
    def get_last_health(self) -> Optional[SystemHealth]:
        """Get last system health check result."""
        return self.last_system_health
    
    def get_service_health(self, service_name: str) -> Optional[ServiceHealth]:
        """Get health of specific service."""
        return self.service_healths.get(service_name)
    
    def get_all_services_health(self) -> Dict[str, ServiceHealth]:
        """Get health of all services."""
        return self.service_healths.copy()
    
    def get_error_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent error history."""
        return self.error_history[-limit:]
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get health metrics for monitoring."""
        return {
            "check_count": self.check_count,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "services_count": len(self.service_healths),
            "overall_status": self.last_system_health.overall_status.value if self.last_system_health else None,
            "readiness": self.last_system_health.readiness.value if self.last_system_health else None,
            "error_count": len(self.error_history)
        }


# Global health check service instance
_health_check_service: Optional[HealthCheckService] = None


def get_health_check_service() -> HealthCheckService:
    """Get or create global health check service."""
    global _health_check_service
    if _health_check_service is None:
        _health_check_service = HealthCheckService()
    return _health_check_service


def initialize_health_check_service(
    check_timeout_sec: int = 5,
    failure_threshold: int = 3,
    degraded_response_time_ms: float = 1000.0
) -> HealthCheckService:
    """Initialize health check service with custom config."""
    global _health_check_service
    _health_check_service = HealthCheckService(
        check_timeout_sec=check_timeout_sec,
        failure_threshold=failure_threshold,
        degraded_response_time_ms=degraded_response_time_ms
    )
    return _health_check_service


def check_redis_health(redis_client: Any) -> str:
    """
    Pings Redis and verifies if caching state is UP/DOWN.
    Returns "up" or "down".
    """
    if redis_client is None:
        return "down"
    try:
        redis_client.ping()
        return "up"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return "down"


def check_postgres_health(config: Any) -> str:
    """
    Verifies PostgreSQL availability by executing a simple query.
    Returns "up" or "down".
    """
    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 not installed, marking Postgres health as down")
        return "down"

    conn = None
    try:
        conn = psycopg2.connect(
            host=config.pg_host,
            port=config.pg_port,
            database=config.pg_database,
            user=config.pg_user,
            password=config.pg_password,
            connect_timeout=2
        )
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return "up"
    except Exception as e:
        logger.warning(f"Postgres health check failed: {e}")
        return "down"
