"""
GDCE Orchestrator Service v2
Independent microservice for orchestrating queries across retrieval, calculation, and trade data services
"""

__version__ = "2.0.0"
__author__ = "GDCE Team"
__description__ = "Customs and Trade Query Orchestrator"

# Lazy imports - defer loading to avoid circular import issues
# Import only when actually needed by consumers

__all__ = [
    "get_config",
    "OrchestratorConfig",
    "ServiceCoordinator",
    "get_policy_engine",
    "WorkflowIntent",
    "QueryRequest",
    "QueryResponse",
    "HealthCheckResponse",
    "app",
]
