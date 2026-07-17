"""
Infrastructure module - Orchestrator service
Contains service clients and communication adapters
"""

from .clients import (
    BaseServiceClient,
    HttpxServiceClient,
    RetrievalServiceClient,
    CalculatorServiceClient,
    TradeDataServiceClient,
    ServiceClientFactory,
    ServiceRegistry,
    get_service_registry,
    initialize_service_clients,
)

from .health_checks import (
    ServiceHealthStatus,
    SystemReadiness,
    ServiceHealth,
    SystemHealth,
    HealthCheckService,
    get_health_check_service,
    initialize_health_check_service,
)

from .database import (
    Base,
    engine,
    SessionLocal,
    get_db,
    get_db_context,
    check_and_create_db,
    session_id_var,
    message_id_var,
)
from .models import (
    ChatSession,
    ChatMessage,
    SessionContextModel,
    IntentRoute,
    ServiceCall,
    ConversationSummary,
    ChatFeedback,
    ChatAttachment,
    FailedRequest,
    ModelUsageLog,
)

__all__ = [
    "BaseServiceClient",
    "HttpxServiceClient",
    "RetrievalServiceClient",
    "CalculatorServiceClient",
    "TradeDataServiceClient",
    "ServiceClientFactory",
    "ServiceRegistry",
    "get_service_registry",
    "initialize_service_clients",
    "ServiceHealthStatus",
    "SystemReadiness",
    "ServiceHealth",
    "SystemHealth",
    "HealthCheckService",
    "get_health_check_service",
    "initialize_health_check_service",
    # Database exports
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "get_db_context",
    "check_and_create_db",
    "session_id_var",
    "message_id_var",

    # Model exports
    "ChatSession",
    "ChatMessage",
    "SessionContextModel",
    "IntentRoute",
    "ServiceCall",
    "ConversationSummary",
    "ChatFeedback",
    "ChatAttachment",
    "FailedRequest",
    "ModelUsageLog",
]

