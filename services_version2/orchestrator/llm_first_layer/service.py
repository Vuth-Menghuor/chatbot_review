"""
Main facade for the unified LLM first layer service.

Exposes a single interface for validation, intent detection, ambiguity checking,
currency detection, and query rewriting.
"""

import logging
from typing import Optional, Any, List, Dict

class AskBackResult:
    def __init__(
        self,
        should_ask_back: bool,
        question: str,
        candidate_intents: List[str],
        trigger_reason: str,
    ):
        self.should_ask_back = should_ask_back
        self.question = question
        self.candidate_intents = candidate_intents
        self.trigger_reason = trigger_reason


class AskBackTemplate:
    def generate(self, query: str, candidate_intents: List[str], session: Any) -> str:
        intent_map = {
            "trade": "trade data",
            "trade_query": "trade data",
            "hs_code_lookup": "hs code lookup",
            "general": "general question",
            "calculation": "calculation",
        }
        options = [intent_map.get(c, c) for c in candidate_intents]
        if len(options) > 1:
            options_str = ", ".join(options[:-1]) + ", or " + options[-1]
        else:
            options_str = options[0] if options else ""
        return f"Would that be related to {options_str}?"


from .config import LLMFirstLayerConfig
from .models import FirstLayerResult
from .pipeline import FirstLayerPipeline

logger = logging.getLogger(__name__)


class LLMFirstLayerService:
    """
    Unified first LLM layer service.
    
    Orchestrates:
    - Input validation
    - Intent detection (Gemini primary)
    - Ambiguity checking
    - Currency detection
    - Query rewriting (Gemini)
    
    All operations happen in one coordinated pipeline with minimal LLM calls.
    """

    def __init__(self, config: Optional[Any] = None):
        from .config import LLMFirstLayerConfig
        
        if config is None:
            self.config = LLMFirstLayerConfig()
        elif isinstance(config, LLMFirstLayerConfig):
            self.config = config
        else:
            # Convert legacy configuration to LLMFirstLayerConfig
            self.config = LLMFirstLayerConfig()
            if hasattr(config, "provider"):
                self.config.intent_provider = config.provider
            if hasattr(config, "timeout"):
                self.config.intent_timeout = config.timeout
                self.config.rewrite_timeout = config.timeout
                self.config.currency_timeout = config.timeout
            # Copy other matching attributes
            for key in self.config.__dict__.keys():
                if hasattr(config, key):
                    setattr(self.config, key, getattr(config, key))
                    
        self.pipeline = FirstLayerPipeline(self.config)
        self._in_detect_intent = False
        self._in_detect_currency = False
        self._in_rewrite_input = False
        
        # Initialize session manager
        from ..core.input_rewriter import SessionManager
        self.session_manager = SessionManager()
        self._template = AskBackTemplate()
        
        logger.info("LLM First Layer Service initialized")

    def get_or_create_session(self, session_id: str) -> Any:
        """Retrieve or create session context for a session ID."""
        return self.session_manager.get_or_create_session(session_id)

    def update_session_context(self, session_id: str, **kwargs: Any) -> None:
        """Update session context attributes."""
        self.session_manager.update_session_context(session_id, **kwargs)

    def _get_llm_service(self):
        """Helper to get/create LLM service with first layer config."""
        from ..llm_service.service import get_llm_service, LLMServiceConfig
        import services_version2.orchestrator.llm_service.service as llm_service_mod
        
        # Build LLM service config based on first layer config
        llm_config = LLMServiceConfig(
            intent_provider=self.config.intent_provider,
            currency_provider=self.config.currency_provider,
            rewrite_provider=self.config.rewrite_provider,
            gemini_api_key=self.config.gemini_api_key,
            gemini_model=self.config.gemini_model,
            gemini_timeout=self.config.intent_timeout,
        )
        
        if llm_service_mod._llm_service_instance is not None:
            existing = llm_service_mod._llm_service_instance
            if not getattr(existing.config, "gemini_api_key", None) and self.config.gemini_api_key:
                llm_service_mod._llm_service_instance = None
            elif getattr(existing.config, "intent_provider", "") == "ollama" and self.config.intent_provider == "gemini":
                llm_service_mod._llm_service_instance = None

        return get_llm_service(llm_config)

    def is_available(self) -> bool:
        """Check if the service is operational."""
        try:
            return self._get_llm_service().is_available()
        except Exception:
            return False

    def detect_intent(self, question: str) -> tuple:
        """Compatibility wrapper for legacy detect_intent callers."""
        from ..core.workflow import WorkflowIntent
        
        if self._in_detect_intent:
            logger.warning("Recursion detected in detect_intent, falling back to keyword matching")
            from ..core.workflow import WorkflowExecutor
            executor = WorkflowExecutor(use_llm_intent=False)
            return executor._keyword_based_intent_detection(question), 1.0, "Recursion fallback"
            
        self._in_detect_intent = True
        try:
            llm_service = self._get_llm_service()
            intent_str, confidence, reasoning = llm_service.classify_intent(question)
            
            try:
                intent = WorkflowIntent(intent_str)
            except ValueError:
                intent = WorkflowIntent.UNCLASSIFIED
                
            return intent, confidence, reasoning
        finally:
            self._in_detect_intent = False

    def detect_currency(self, question: str) -> tuple:
        """Compatibility wrapper for legacy detect_currency callers."""
        if self._in_detect_currency:
            logger.warning("Recursion detected in detect_currency, falling back to pattern matching")
            from ..core.workflow import WorkflowExecutor
            executor = WorkflowExecutor(use_llm_intent=False)
            return executor._pattern_based_currency_detection(question)

        self._in_detect_currency = True
        try:
            llm_service = self._get_llm_service()
            return llm_service.detect_currency(question)
        finally:
            self._in_detect_currency = False

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
    ) -> tuple:
        """Compatibility wrapper for legacy rewrite_input callers."""
        if self._in_rewrite_input:
            logger.warning("Recursion detected in rewrite_input, skipping rewrite")
            return user_input, {"rewrite_reason": "recursion_fallback", "confidence": 1.0, "was_rewritten": False}

        self._in_rewrite_input = True
        try:
            llm_service = self._get_llm_service()
            return await llm_service.rewrite_input(
                user_input=user_input,
                context=context,
                intent_hint=intent_hint,
            )
        finally:
            self._in_rewrite_input = False

    async def process(
        self,
        query: str,
        request_id: str,
        session_context: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> FirstLayerResult:
        """
        Process a user query through the unified first LLM layer.
        
        This is the main entry point for the orchestrator.
        
        Args:
            query: User input query
            request_id: Correlation ID for request tracing
            session_context: Optional session context for multi-turn
            session_id: Optional session ID
            
        Returns:
            FirstLayerResult containing:
            - validation status
            - detected intent and confidence
            - ambiguity check result
            - detected currency
            - rewritten query (if applicable)
            - processing metadata
        """
        return await self.pipeline.process(
            query=query,
            request_id=request_id,
            session_context=session_context,
            session_id=session_id,
        )

    async def get_clarification_async(
        self,
        query: str,
        intent_label: str,
        confidence: float,
        session: Any,
        candidate_scores: Optional[Dict[str, float]] = None,
        turn_number: int = 1,
    ) -> AskBackResult:
        """Assess if query is ambiguous and requires ask-back clarification."""
        if not candidate_scores:
            from ..core.workflow import WorkflowExecutor
            executor = WorkflowExecutor(use_llm_intent=False)
            candidate_scores = executor._estimate_candidate_scores(query)

        # We present the core candidates
        candidates = ["trade_query", "hs_code_lookup", "general", "calculation"]
        
        question_text = self._template.generate(query, candidates, session)
        
        # A turn-2+ fragment (e.g. low confidence or non-core) triggers ask-back
        q_lower = query.lower().strip()
        is_followup = any(q_lower.startswith(pat) for pat in ["what about", "how about", "and for", "for"])
        should_ask_back = is_followup or confidence < 0.75 or intent_label in {"small_talk", "unclassified"}
        
        return AskBackResult(
            should_ask_back=should_ask_back,
            question=question_text,
            candidate_intents=candidates,
            trigger_reason="followup_fragment" if is_followup else "low_confidence_fragment" if should_ask_back else "none"
        )

    def resolve_from_user_response(
        self, user_text: str, candidate_intents: List[str]
    ) -> Optional[str]:
        """Map user's choice back to one of the candidate intents."""
        text = user_text.lower().strip()
        
        mapping = {
            "trade": "trade_query",
            "trade data": "trade_query",
            "statistics": "trade_query",
            "volume": "trade_query",
            "hs": "hs_code_lookup",
            "hs code": "hs_code_lookup",
            "code": "hs_code_lookup",
            "lookup": "hs_code_lookup",
            "classify": "hs_code_lookup",
            "general": "general",
            "general question": "general",
            "policy": "general",
            "procedure": "general",
            "calculation": "calculation",
            "tax": "calculation",
            "duty": "calculation",
            "calculate": "calculation"
        }
        
        for key, val in mapping.items():
            if key in text and val in candidate_intents:
                return val
                
        for candidate in candidate_intents:
            if candidate.lower() in text:
                return candidate
                
        return None


# Singleton management
_first_layer_instance: Optional[LLMFirstLayerService] = None


def get_llm_first_layer_service(
    config: Optional[LLMFirstLayerConfig] = None,
) -> LLMFirstLayerService:
    """Get or create the singleton LLM first layer service."""
    global _first_layer_instance
    if _first_layer_instance is None:
        _first_layer_instance = LLMFirstLayerService(config)
    return _first_layer_instance
