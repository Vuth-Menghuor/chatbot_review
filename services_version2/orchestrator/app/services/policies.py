"""
Policies Module - Orchestrator service
Implements orchestration policies, rules, and decision logic
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class PolicyType(str, Enum):
    """Types of policies."""
    INTENT_ROUTING = "intent_routing"
    RETRY = "retry"
    FALLBACK = "fallback"
    VALIDATION = "validation"
    SECURITY = "security"
    ASK_BACK = "ask_back"   # clarification round-trip policy


@dataclass
class Policy:
    """Base policy class."""
    name: str
    policy_type: PolicyType
    enabled: bool = True
    priority: int = 0
    
    def apply(self, context: Dict[str, Any]) -> bool:
        """
        Apply policy to context.
        
        Args:
            context: Execution context
            
        Returns:
            True if policy applies, False otherwise
        """
        raise NotImplementedError


class IntentRoutingPolicy(Policy):
    """
    Policy for intent-based routing.
    Defines how questions are routed to services based on detected intent.
    """
    
    def __init__(self, routes: Dict[str, List[str]]):
        """
        Initialize intent routing policy.
        
        Args:
            routes: Mapping of intent to list of services
        """
        super().__init__(
            name="intent_routing",
            policy_type=PolicyType.INTENT_ROUTING,
            priority=10
        )
        self.routes = routes
    
    def get_route(self, intent: str) -> List[str]:
        """
        Get service route for intent.
        
        Args:
            intent: Detected intent
            
        Returns:
            List of services to call
        """
        return self.routes.get(intent, ["retrieval"])
    
    def apply(self, context: Dict[str, Any]) -> bool:
        """Apply routing policy."""
        if "intent" not in context:
            return False
        
        intent = context["intent"]
        route = self.get_route(intent)
        context["route"] = route
        return True


class ValidationPolicy(Policy):
    """
    Policy for input validation.
    Defines validation rules for different intent types.
    """
    
    def __init__(self):
        """Initialize validation policy."""
        super().__init__(
            name="validation",
            policy_type=PolicyType.VALIDATION,
            priority=5
        )
        self.rules = {
            "calculation": self._validate_calculation,
            "trade_query": self._validate_trade_query,
            "definition": self._validate_definition,
        }
    
    def _validate_calculation(self, question: str) -> tuple:
        """
        Validate calculation question.
        
        Returns:
            (is_valid: bool, missing_fields: List[str])
        """
        import re
        
        q_lower = question.lower()
        missing = []
        
        # Check for numeric value
        if not re.search(r'\d+(\.\d+)?', q_lower):
            missing.append("numeric_value")
        
        # Check for product/item (include exemption-related terms as product signals)
        product_keywords = [
            "import", "export", "product", "goods", "item",
            "from", "origin", "country", "hs", "laptop", "phone", "car",
            "rubber", "rice", "machinery", "equipment", "material",
            "qip", "sez", "diplomatic", "embassy", "ngo", "university",
            "hospital", "medical", "passenger", "luggage", "fta",
        ]
        if not any(kw in q_lower for kw in product_keywords):
            missing.append("product_reference")
        
        return len(missing) == 0, missing if missing else None
    
    def _validate_trade_query(self, question: str) -> tuple:
        """
        Validate trade query.
        
        Returns:
            (is_valid: bool, issues: List[str])
        """
        q_lower = question.lower()
        
        # Trade queries just need keywords, very lenient
        trade_keywords = ["trade", "export", "import", "shipping", "cargo"]
        if any(kw in q_lower for kw in trade_keywords):
            return True, None
        
        return False, ["missing_trade_keywords"]
    
    def _validate_definition(self, question: str) -> tuple:
        """
        Validate definition question.
        
        Returns:
            (is_valid: bool, issues: List[str])
        """
        # Definition questions are always valid
        return True, None
    
    def validate(self, question: str, intent: str) -> tuple:
        """
        Validate question for given intent.
        
        Args:
            question: User question
            intent: Detected intent
            
        Returns:
            (is_valid: bool, missing_fields: List[str])
        """
        validator = self.rules.get(intent)
        if not validator:
            return True, None
        
        return validator(question)
    
    def apply(self, context: Dict[str, Any]) -> bool:
        """Apply validation policy."""
        if "question" not in context or "intent" not in context:
            return False
        
        is_valid, issues = self.validate(context["question"], context["intent"])
        context["validation_passed"] = is_valid
        context["validation_issues"] = issues
        return is_valid


class RetryPolicy(Policy):
    """
    Policy for retry behavior.
    Defines retry attempts, backoff, and circuit breaker rules.
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        backoff_strategy: str = "exponential",
        backoff_factor: float = 2.0
    ):
        """
        Initialize retry policy.
        
        Args:
            max_retries: Maximum retry attempts
            backoff_strategy: Strategy for backoff (exponential, linear, constant)
            backoff_factor: Factor for backoff calculation
        """
        super().__init__(
            name="retry",
            policy_type=PolicyType.RETRY,
            priority=8
        )
        self.max_retries = max_retries
        self.backoff_strategy = backoff_strategy
        self.backoff_factor = backoff_factor
    
    def get_backoff_delay(self, attempt: int, base_delay: float = 0.1) -> float:
        """
        Calculate backoff delay for attempt.
        
        Args:
            attempt: Attempt number (0-indexed)
            base_delay: Base delay in seconds
            
        Returns:
            Delay in seconds
        """
        if self.backoff_strategy == "exponential":
            return base_delay * (self.backoff_factor ** attempt)
        elif self.backoff_strategy == "linear":
            return base_delay * (attempt + 1) * self.backoff_factor
        else:  # constant
            return base_delay
    
    def apply(self, context: Dict[str, Any]) -> bool:
        """Apply retry policy."""
        context["max_retries"] = self.max_retries
        context["backoff_strategy"] = self.backoff_strategy
        return True


class FallbackPolicy(Policy):
    """
    Policy for fallback behavior.
    Defines fallback service choices when primary fails.
    """
    
    def __init__(self, fallback_map: Optional[Dict[str, str]] = None):
        """
        Initialize fallback policy.
        
        Args:
            fallback_map: Mapping of intent to fallback intent
        """
        super().__init__(
            name="fallback",
            policy_type=PolicyType.FALLBACK,
            priority=9
        )
        self.fallback_map = fallback_map or {
            "calculation": "retrieval",
            "trade_query": "retrieval",
            "policy_query": "definition",
        }
    
    def get_fallback(self, intent: str) -> Optional[str]:
        """
        Get fallback option for failed intent.
        
        Args:
            intent: Original intent
            
        Returns:
            Fallback intent or None
        """
        return self.fallback_map.get(intent)
    
    def apply(self, context: Dict[str, Any]) -> bool:
        """Apply fallback policy."""
        if "intent" not in context or "failed" not in context:
            return False
        
        if not context["failed"]:
            return False
        
        fallback = self.get_fallback(context["intent"])
        if fallback:
            context["fallback_intent"] = fallback
            return True
        
        return False


class PolicyEngine:
    """
    Central policy engine for orchestrator.
    Manages and applies policies consistently across the service.
    """

    # ── lazy import to avoid circular deps ──────────────────────────────
    @staticmethod
    def _load_ask_back_policy():
        from ..ai import get_llm_first_layer_service as get_ask_back_service
        return get_ask_back_service()
    
    def __init__(self, repo_root: Optional[Path] = None):
        """
        Initialize policy engine.
        
        Args:
            repo_root: Repository root path for loading policy files
        """
        self.repo_root = repo_root or Path(__file__).resolve().parents[3]
        self.policies: Dict[str, Policy] = {}
        self._register_default_policies()
        self._load_policy_files()
    
    def _register_default_policies(self):
        """Register default policies."""
        # Intent routing
        self.register_policy(IntentRoutingPolicy({
            "calculation": ["calculator"],
            "trade_query": ["trade_data"],
            "definition": ["retrieval"],
            "policy_query": ["retrieval"],
        }))

        # Validation
        self.register_policy(ValidationPolicy())

        # Retry
        self.register_policy(RetryPolicy(
            max_retries=3,
            backoff_strategy="exponential"
        ))

        # Fallback
        self.register_policy(FallbackPolicy())

        # Ask-back clarification (lazy-loaded to avoid circular import)
        try:
            self.ask_back_policy = self._load_ask_back_policy()
            logger.info("Registered policy: ask_back (type: ask_back)")
        except Exception as e:
            logger.warning(f"AskBackPolicy could not be loaded: {e}")
            self.ask_back_policy = None
    
    def _load_policy_files(self):
        """Load policies from policy files (if they exist)."""
        policy_dir = self.repo_root / "model" / "orchestration"
        
        if not policy_dir.exists():
            logger.info(f"Policy directory not found: {policy_dir}")
            return
        
        # Load intent routing rules
        intent_routing_file = policy_dir / "intent_routing_rules.md"
        if intent_routing_file.exists():
            try:
                logger.info(f"Loading intent routing rules from {intent_routing_file}")
            except Exception as e:
                logger.warning(f"Could not load intent routing rules: {e}")
    
    def register_policy(self, policy: Policy):
        """
        Register a policy.
        
        Args:
            policy: Policy instance
        """
        if not policy.enabled:
            return
        
        self.policies[policy.name] = policy
        logger.info(f"Registered policy: {policy.name} (type: {policy.policy_type})")
    
    def apply_policies(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply all relevant policies to context.
        Policies are applied in priority order.
        
        Args:
            context: Execution context
            
        Returns:
            Updated context
        """
        # Sort by priority (higher first)
        sorted_policies = sorted(
            self.policies.values(),
            key=lambda p: p.priority,
            reverse=True
        )
        
        for policy in sorted_policies:
            try:
                policy.apply(context)
            except Exception as e:
                logger.error(f"Error applying policy {policy.name}: {e}")
        
        return context
    
    def detect_intent_policy_based(self, question: str) -> str:
        """
        Detect intent using policy-based rules.
        Falls back to simple heuristics if policy engine not available.

        Args:
            question: User question

        Returns:
            Detected intent
        """
        q_lower = question.lower()

        # Expanded calculation keywords including exemptions, FTA, export
        calc_keywords = [
            "calculate", "compute", "how much", "cost", "duty", "tax",
            "import tax", "export tax", "tariff", "dues",
            "qip", "qualified investment",
            "sez", "special economic zone",
            "diplomatic", "embassy", "consulate",
            "ngo", "unicef", "humanitarian", "relief", "donation",
            "university", "school", "educational", "education",
            "hospital", "medical", "health", "donated",
            "passenger", "luggage", "personal effects",
            "fta", "acfta", "atiga", "rcep", "preferential",
            "dq", "deal", "quote agreement",
            "cif", "declared value",
        ]
        if any(kw in q_lower for kw in calc_keywords):
            return "calculation"

        # Trade data queries (narrower than before — avoid catching generic import/export)
        trade_keywords = [
            "trade volume", "trade data", "trade statistics", "trade route",
            "shipping", "transport", "cargo", "freight", "trade flow",
        ]
        if any(kw in q_lower for kw in trade_keywords):
            return "trade_query"

        if any(kw in q_lower for kw in ["what is", "define", "explain"]):
            return "definition"

        return "policy_query"
    
    def validate_input(self, question: str, intent: str) -> tuple:
        """
        Validate input using policy.
        
        Args:
            question: User question
            intent: Detected intent
            
        Returns:
            (is_valid: bool, issues: List[str])
        """
        validation_policy = self.policies.get("validation")
        if validation_policy:
            return validation_policy.validate(question, intent)
        
        return True, None


def get_policy_engine(repo_root: Optional[Path] = None) -> PolicyEngine:
    """
    Get or create policy engine instance.
    
    Args:
        repo_root: Optional repository root path
        
    Returns:
        PolicyEngine instance
    """
    return PolicyEngine(repo_root)
