"""Data models for the unified LLM first layer."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class ValidationStatus(str, Enum):
    """Validation result status."""
    VALID = "valid"
    INVALID = "invalid"
    AMBIGUOUS = "ambiguous"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class ValidationResult:
    """Result from input validation stage."""
    status: ValidationStatus
    reason: Optional[str] = None
    confidence: float = 1.0


@dataclass
class IntentResult:
    """Result from intent detection stage."""
    intent: str  # e.g., "hs_code_lookup", "calculation", "trade_query", "definition", "policy_query"
    confidence: float  # 0.0-1.0
    reasoning: str
    provider: str = "gemini"  # Which provider was used


@dataclass
class AmbiguityCheckResult:
    """Result from ambiguity check stage."""
    should_ask_back: bool
    trigger_reason: Optional[str] = None  # e.g., "low_confidence", "score_gap", "multiple_interpretations"
    clarification_question: Optional[str] = None
    candidate_intents: List[str] = field(default_factory=list)
    provider: str = "rule_based"


@dataclass
class CurrencyResult:
    """Result from currency detection stage."""
    currency: Optional[str] = None  # e.g., "USD", "KHR", "EUR"
    confidence: float = 0.0
    reasoning: str = ""
    provider: str = "minilm"


@dataclass
class RewriteResult:
    """Result from query rewriting stage."""
    original_query: str
    rewritten_query: str
    was_rewritten: bool
    reason: str = ""
    provider: str = "gemini"


@dataclass
class FirstLayerResult:
    """
    Complete result from the first LLM layer.
    
    Contains all processing results needed for service routing and execution.
    """
    # Input
    original_query: str
    request_id: str
    
    # Validation
    validation: ValidationResult
    
    # Intent Detection
    intent: IntentResult
    
    # Ambiguity Check
    ambiguity: AmbiguityCheckResult
    
    # Currency Detection
    currency: CurrencyResult
    
    # Query Rewriting
    rewrite: RewriteResult
    
    # Processing metadata
    processing_time_ms: float = 0.0
    all_providers_used: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    # Session context
    session_context: Optional[Any] = None
    session_id: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if query passed validation."""
        return self.validation.status == ValidationStatus.VALID
    
    @property
    def needs_clarification(self) -> bool:
        """Check if clarification is needed."""
        return self.ambiguity.should_ask_back
    
    @property
    def final_query(self) -> str:
        """Get the query to use for routing (original or rewritten)."""
        return self.rewrite.rewritten_query if self.rewrite.was_rewritten else self.original_query
