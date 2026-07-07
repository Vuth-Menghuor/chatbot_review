"""
Domain Models for Orchestrator Service

Defines core business logic data structures:
  - Workflow management (context, state, results)
  - Intent detection data
  - Service coordination models
  - Policy and configuration models
"""

from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import time


# Enums

class ServiceType(str, Enum):
    """Supported downstream services."""
    CALCULATOR = "calculator"
    RETRIEVAL = "retrieval"
    TRADE_DATA = "trade_data"
    GENERAL = "general"


class WorkflowIntentType(str, Enum):
    """Supported workflow intents."""
    CALCULATION = "calculation"
    TRADE_QUERY = "trade_query"
    HS_CODE_LOOKUP = "hs_code_lookup"
    GENERAL = "general"


class WorkflowStatusType(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CLARIFICATION_REQUIRED = "clarification_required"


class IntentDetectionSourceType(str, Enum):
    """Source of intent detection result."""
    LLM_PRIMARY = "layer_1_llm"
    KEYWORD_EXACT = "layer_2_keyword_exact"
    PATTERN_MATCH = "layer_2_pattern_regex"
    COMPOUND_RULE = "layer_2_compound_rule"
    FALLBACK = "layer_2_fallback"
    ERROR = "error"


class ServiceCallStatusType(str, Enum):
    """Status of individual service call."""
    PENDING = "pending"
    CALLING = "calling"
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"


# Configuration Models

@dataclass
class ServiceConfig:
    """Configuration for downstream service."""
    host: str
    port: int
    timeout_ms: int = 30000 # how many times to retry on network failures.
    max_retries: int = 3
    retry_backoff_ms: int = 100
    enabled: bool = True
    
    @property
    def base_url(self) -> str:
        """Get service base URL."""
        return f"http://{self.host}:{self.port}"
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.host:
            raise ValueError("Service host is required")
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")


@dataclass
class IntentDetectionConfig:
    """Configuration for intent detection."""
    llm_enabled: bool = True
    llm_confidence_threshold: float = 0.75
    llm_timeout_ms: int = 2000
    keyword_detection_enabled: bool = True
    keyword_match_timeout_ms: int = 500
    fallback_intent: str = "general"


@dataclass
class ValidationConfig:
    """Configuration for input/output validation."""
    validate_input: bool = True
    validate_output: bool = True
    security_checks_enabled: bool = True
    max_question_length: int = 2000
    min_question_length: int = 2


# Intent Detection Models

@dataclass
class IntentDetectionResult:
    """
    Result from intent detection pipeline.
    Determines which WorkflowSequence service chain will be loaded.
    """
    intent: WorkflowIntentType
    confidence: float                       # Confidence score (0.0 to 1.0)
    source: IntentDetectionSourceType       # Mechanism used (LLM vs keyword/rule fallback)
    reasoning: str                          # Trace explanation of why this intent was matched
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        """String representation."""
        return (f"Intent={self.intent.value} | Confidence={self.confidence:.2f} | "
                f"Source={self.source.value} | {self.reasoning[:50]}")
    
    @property
    def is_high_confidence(self) -> bool:
        """Check if confidence is high (>= 0.85)."""
        return self.confidence >= 0.85
    
    @property
    def is_acceptable_confidence(self) -> bool:
        """Check if confidence is acceptable (>= 0.75)."""
        return self.confidence >= 0.75


# Service Call Models

@dataclass
class ServiceCallRequest:
    """Request payload for downstream services."""
    service_type: ServiceType
    endpoint: str
    method: str = "POST"
    body: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timeout_ms: int = 30000
    
    def __post_init__(self):
        """Initialize defaults."""
        if not self.headers:
            self.headers = {"Content-Type": "application/json"}


@dataclass
class ServiceCallResult:
    """
    Result from downstream microservice execution.
    Captured in WorkflowContext to make responses available for downstream services.
    """
    service_type: ServiceType
    status: ServiceCallStatusType
    response_time_ms: float
    data: Optional[Dict[str, Any]] = None       # HTTP JSON response payload
    error: Optional[str] = None                 # Error log details if status is failed/timeout
    http_status_code: Optional[int] = None      # Returned HTTP status code
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_success(self) -> bool:
        """Check if call was successful (status is SUCCESS)."""
        return self.status == ServiceCallStatusType.SUCCESS
    
    @property
    def is_error(self) -> bool:
        """Check if call resulted in error or timeout."""
        return self.status in [ServiceCallStatusType.ERROR, ServiceCallStatusType.TIMEOUT]


# Workflow Models

@dataclass
class WorkflowSequence:
    """
    Sequence of service calls representing the execution path for a given intent.
    - primary_service: Executed first in the chain.
    - secondary_services: Executed sequentially if the previous ones succeeded.
    - fallback_service: Executed if the primary service fails.
    """
    primary_service: ServiceType
    secondary_services: List[ServiceType] = field(default_factory=list)
    fallback_service: ServiceType = ServiceType.RETRIEVAL
    description: str = ""
    
    def get_service_chain(self) -> List[ServiceType]:
        """Returns the full sequence list of services to call."""
        return [self.primary_service] + self.secondary_services


@dataclass
class WorkflowContext:
    """
    Main Context for Workflow Execution.
    Maintains the state, metadata, and responses for the query's end-to-end execution.
    Passed as the single source of truth across service executors.
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    question: str = ""
    session_id: Optional[str] = None
    
    # Intent detection states
    detected_intent: Optional[IntentDetectionResult] = None
    workflow_sequence: Optional[WorkflowSequence] = None
    
    # Execution outputs from microservices
    service_results: Dict[ServiceType, ServiceCallResult] = field(default_factory=dict)
    calculation_result: Optional[Dict[str, Any]] = None
    retrieval_result: Optional[Dict[str, Any]] = None
    trade_query_result: Optional[Dict[str, Any]] = None
    
    # Status and alerts
    status: WorkflowStatusType = WorkflowStatusType.PENDING
    errors: List[str] = field(default_factory=list)
    clarifications: List[str] = field(default_factory=list)     # Clarification prompts (ask-back)
    warnings: List[str] = field(default_factory=list)
    
    # Latency tracking
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Extra request metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    
    @property
    def latency_ms(self) -> float:
        """Calculates total processing latency in milliseconds."""
        if not self.started_at or not self.completed_at:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds() * 1000
    
    @property
    def is_completed(self) -> bool:
        """Returns True if the workflow has hit a terminal execution state."""
        return self.status in [
            WorkflowStatusType.COMPLETED,
            WorkflowStatusType.FAILED,
            WorkflowStatusType.PARTIAL,
            WorkflowStatusType.CLARIFICATION_REQUIRED
        ]
    
    @property
    def is_successful(self) -> bool:
        """Returns True if the workflow completed successfully without terminal failures."""
        return self.status == WorkflowStatusType.COMPLETED
    
    @property
    def has_errors(self) -> bool:
        """Returns True if any unrecoverable errors occurred."""
        return len(self.errors) > 0
    
    def add_error(self, error: str):
        """Records an error and updates status to FAILED if pending."""
        self.errors.append(error)
        if self.status == WorkflowStatusType.PENDING:
            self.status = WorkflowStatusType.FAILED
    
    def add_clarification(self, clarification: str):
        """Records a clarification question (ask-back) and sets the corresponding status."""
        self.clarifications.append(clarification)
        self.status = WorkflowStatusType.CLARIFICATION_REQUIRED
    
    def add_warning(self, warning: str):
        """Records a non-terminal warning."""
        self.warnings.append(warning)
    
    def set_service_result(self, service_type: ServiceType, result: ServiceCallResult):
        """Caches service call result inside context mappings."""
        self.service_results[service_type] = result
    
    def get_service_result(self, service_type: ServiceType) -> Optional[ServiceCallResult]:
        """Fetches completed result for a specific service."""
        return self.service_results.get(service_type)
    
    def mark_started(self):
        """Transitions status to IN_PROGRESS and records starting time."""
        self.started_at = datetime.utcnow()
        self.status = WorkflowStatusType.IN_PROGRESS
    
    def mark_completed(self, success: bool = True):
        """Sets completed time and updates status based on success/failure."""
        self.completed_at = datetime.utcnow()
        if success:
            self.status = WorkflowStatusType.COMPLETED
        else:
            if not self.has_errors and self.status != WorkflowStatusType.CLARIFICATION_REQUIRED:
                self.status = WorkflowStatusType.FAILED
    
    def to_dict(self) -> Dict[str, Any]:
        """Converts context context info into JSON serializable format."""
        return {
            "request_id": self.request_id,
            "question": self.question,
            "session_id": self.session_id,
            "intent": self.detected_intent.intent.value if self.detected_intent else None,
            "status": self.status.value,
            "errors": self.errors,
            "clarifications": self.clarifications,
            "warnings": self.warnings,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
        }


@dataclass
class WorkflowPolicy:
    """Policy for workflow execution."""
    name: str
    intent: WorkflowIntentType
    service_sequence: WorkflowSequence
    retry_policy: Dict[str, Any] = field(default_factory=dict)
    caching_policy: Dict[str, Any] = field(default_factory=dict)
    timeout_policy: Dict[str, Any] = field(default_factory=dict)
    fallback_policy: Dict[str, Any] = field(default_factory=dict)
    
    def should_retry_on_error(self, service_type: ServiceType) -> bool:
        """Check if service call should be retried on error."""
        retry_policy = self.retry_policy or {}
        return retry_policy.get("enabled", True)


# Response Models

@dataclass
class IntentExplanation:
    """Explanation of intent detection."""
    detected_intent: WorkflowIntentType
    confidence: float
    source: IntentDetectionSourceType
    reasoning: str
    alternative_intents: List[tuple] = field(default_factory=list)  # [(intent, confidence)]
    workflow_description: str = ""


@dataclass
class QueryExplanation:
    """Detailed explanation of query processing."""
    request_id: str
    question: str
    intent_explanation: IntentExplanation
    service_calls: List[Dict[str, Any]] = field(default_factory=list)
    total_latency_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Validation Models

@dataclass
class ValidationResult:
    """Result of validation check."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def has_errors(self) -> bool:
        """Check if validation has errors."""
        return len(self.errors) > 0


@dataclass
class InputValidationResult(ValidationResult):
    """Result of input validation."""
    missing_fields: List[str] = field(default_factory=list)
    has_security_issues: bool = False
    sanitized_question: Optional[str] = None


@dataclass
class OutputValidationResult(ValidationResult):
    """Result of output validation."""
    response_valid: bool = True
    structure_valid: bool = True
    required_fields_present: bool = True


# Caching Models

@dataclass
class CacheEntry:
    """Cache entry for query results."""
    key: str
    value: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int = 3600
    hits: int = 0
    
    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        elapsed = (datetime.utcnow() - self.timestamp).total_seconds()
        return elapsed > self.ttl_seconds
    
    def increment_hits(self):
        """Increment hit counter."""
        self.hits += 1


# Audit & Logging Models

@dataclass
class AuditLog:
    """Audit log entry."""
    request_id: str
    timestamp: datetime
    action: str  # "query_received", "intent_detected", "service_called", etc.
    service: Optional[ServiceType] = None
    status: str = "info"  # info, warning, error
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "service": self.service.value if self.service else None,
            "status": self.status,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


# Utility Functions

def create_workflow_context(question: str, session_id: Optional[str] = None) -> WorkflowContext:
    """
    Factory function to create a workflow context.
    
    Args:
        question: User question
        session_id: Optional session ID
        
    Returns:
        Initialized WorkflowContext
    """
    context = WorkflowContext(
        question=question,
        session_id=session_id or None,
    )
    return context


def create_service_result(
    service_type: ServiceType,
    success: bool,
    data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    response_time_ms: float = 0.0,
    http_status: Optional[int] = None,
) -> ServiceCallResult:
    """
    Factory function to create a service call result.
    
    Args:
        service_type: Type of service
        success: Whether call was successful
        data: Response data (if successful)
        error: Error message (if failed)
        response_time_ms: Response time
        http_status: HTTP status code (if applicable)
        
    Returns:
        ServiceCallResult
    """
    if success:
        status = ServiceCallStatusType.SUCCESS
    elif error and "timeout" in error.lower():
        status = ServiceCallStatusType.TIMEOUT
    else:
        status = ServiceCallStatusType.ERROR
    
    return ServiceCallResult(
        service_type=service_type,
        status=status,
        response_time_ms=response_time_ms,
        data=data,
        error=error,
        http_status_code=http_status,
    )
