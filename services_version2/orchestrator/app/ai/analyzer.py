"""
Unified LLM first-layer service and pipeline.

Coordinates validation, intent detection, ambiguity checking, 
currency detection, and query rewriting in a single unified flow.
"""

import asyncio
import logging
import contextvars
import time
import re
from typing import Optional, Any, Tuple, Dict

from ..core.config import LLMFirstLayerConfig
from ..schemas.ai_models import (
    FirstLayerResult,
    ValidationResult,
    ValidationStatus,
    IntentResult,
    AmbiguityCheckResult,
    CurrencyResult,
    RewriteResult,
)

from prompts.dynamic_prompt_manager import DynamicPromptManager

# Module-level prompt manager — loads from prompts/ directory on import
_prompt_manager = DynamicPromptManager()

logger = logging.getLogger(__name__)

# Request-scoped context variable to prevent cross-session concurrent data bleeding
unified_result_var: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "unified_result_var", default=None
)

# Lexical noise patterns for local query stripping
FILLER_PATTERNS = [
    r"\bum+\b", r"\buh+\b", r"\bso\b", r"\blike i said\b", r"\bactually\b",
    r"\bi was wondering\b", r"\bcould you please\b", r"\bkind of\b", r"\bjust\b",
]

# Semantic/narrative noise indicators for triggering LLM cleanup of verbose queries
NARRATIVE_PATTERNS = [
    r"\b(?:my\s+)?(?:partner|colleague|friend|boss|client|customer|brother|sister|family)\b",
    r"\b(?:told|said|mentioned|asked|suggested|recommended|explained)\b",
    r"\b(?:he|she|they)\s+(?:said|told|mentioned|asked|suggested)\b",
    r"\b(?:in\s+my\s+case|for\s+my\s+case|our\s+case)\b",
]

# Shared relative prefixes for follow-up detection
RELATIVE_PREFIXES = ["what about", "how about", "what of", "and for", "then", "also"]


class FirstLayerPipeline:
    """
    Unified pipeline for intent, validation, ambiguity, currency, and rewriting.
    
    Uses minimal LLM calls:
    - Gemini for intent detection and query rewriting
    - Rule-based/regex for validation and ambiguity
    - MiniLM for currency detection (fast pattern matching)
    
    All steps orchestrated in sequence, sharing context and session.
    """

    def __init__(self, config: LLMFirstLayerConfig):
        self.config = config
        
        # Import services lazily to avoid circular dependencies
        self._validator_service = None
        self._intent_service = None
        self._ask_back_service = None
        self._currency_service = None
        self._rewriter_service = None

    @property
    def validator_service(self):
        """Lazy load validator service."""
        if self._validator_service is None:
            from .shims.validator_service import get_input_validator
            self._validator_service = get_input_validator()
        return self._validator_service

    @property
    def intent_service(self):
        """Lazy load intent service."""
        if self._intent_service is None:
            from .shims.intent_service import get_intent_service, IntentServiceConfig
            config = IntentServiceConfig(
                provider=self.config.intent_provider,
                gemini_api_key=self.config.gemini_api_key,
                gemini_model=self.config.gemini_model,
                timeout=self.config.intent_timeout,
            )
            self._intent_service = get_intent_service(config)
        return self._intent_service

    @property
    def rewriter_service(self):
        """Lazy load rewriter service."""
        if self._rewriter_service is None:
            from .shims.rewriter_service import get_rewriter_service, RewriterServiceConfig
            config = RewriterServiceConfig(
                rewrite_provider=self.config.rewrite_provider,
                gemini_api_key=self.config.gemini_api_key,
                gemini_model=self.config.gemini_model,
                gemini_timeout=self.config.rewrite_timeout,
            )
            self._rewriter_service = get_rewriter_service(config)
        return self._rewriter_service

    @property
    def ask_back_service(self):
        """Lazy load ask back service."""
        if self._ask_back_service is None:
            self._ask_back_service = LLMAskBackService(self)
        return self._ask_back_service

    async def process(
        self,
        query: str,
        request_id: str,
        session_context: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> FirstLayerResult:
        """
        [DEPRECATED] Execute the unified first LLM layer pipeline.
        
        Deprecated: Unused in production request lifecycles. Use get_unified_result instead.
        
        Steps:
        1. Validate input
        2. Detect intent (Gemini → fallback to MiniLM/LLM)
        3. Check for ambiguity (rule-based → template/LLM if needed)
        4. Detect currency (MiniLM pattern matching)
        5. Rewrite query (Gemini, conditional)
        
        Args:
            query: User input query
            request_id: Correlation ID for logging
            session_context: Session context (for rewriting and ask-back)
            session_id: Session ID
            
        Returns:
            FirstLayerResult with all processing results
        """
        import warnings
        warnings.warn(
            "FirstLayerPipeline.process is deprecated and unused in production. Use get_unified_result instead.",
            DeprecationWarning,
            stacklevel=2
        )
        start_time = time.time()
        errors = []
        providers_used = set()

        logger.info(f"[{request_id}] Starting unified first layer processing for: {query[:100]}")

        result = FirstLayerResult(
            original_query=query,
            request_id=request_id,
            session_context=session_context,
            session_id=session_id,
            validation=ValidationResult(ValidationStatus.VALID),
            intent=IntentResult("unclassified", 0.0, "Not processed yet"),
            ambiguity=AmbiguityCheckResult(False),
            currency=CurrencyResult(),
            rewrite=RewriteResult(query, query, False),
        )

        try:
            # STEP 1: INPUT VALIDATION
            logger.debug(f"[{request_id}] [1/5] Validating input...")
            try:
                result.validation = await self._step_validate(query)
                providers_used.add("rule_based")
                
                if not result.validation.status == ValidationStatus.VALID:
                    logger.warning(
                        f"[{request_id}] Input validation failed: {result.validation.reason}"
                    )
                    if self.config.fail_fast_on_invalid:
                        result.processing_time_ms = (time.time() - start_time) * 1000
                        result.all_providers_used = list(providers_used)
                        return result
            except Exception as e:
                logger.error(f"[{request_id}] Validation step failed: {e}")
                errors.append(f"validation_error: {e}")
                result.validation = ValidationResult(ValidationStatus.INVALID, str(e))

            # STEP 2: INTENT DETECTION
            logger.debug(f"[{request_id}] [2/5] Detecting intent...")
            try:
                intent_obj = result.intent = await self._step_detect_intent(query)
                providers_used.add(intent_obj.provider)
                logger.info(
                    f"[{request_id}] Intent detected: {intent_obj.intent} "
                    f"(confidence: {intent_obj.confidence:.2f})"
                )
            except Exception as e:
                logger.error(f"[{request_id}] Intent detection failed: {e}")
                errors.append(f"intent_error: {e}")

            # STEP 3: AMBIGUITY CHECK
            logger.debug(f"[{request_id}] [3/5] Checking for ambiguity...")
            try:
                ambiguity_obj = result.ambiguity = await self._step_check_ambiguity(
                    query=query,
                    intent=result.intent.intent,
                    confidence=result.intent.confidence,
                    session_context=session_context,
                )
                providers_used.add(ambiguity_obj.provider)
                
                if ambiguity_obj.should_ask_back:
                    logger.info(
                        f"[{request_id}] Ask-back triggered: {ambiguity_obj.trigger_reason}"
                    )
            except Exception as e:
                logger.error(f"[{request_id}] Ambiguity check failed: {e}")
                errors.append(f"ambiguity_error: {e}")

            # If ambiguity detected, skip remaining steps and return for clarification
            if result.ambiguity.should_ask_back:
                logger.info(f"[{request_id}] Pipeline stopping for clarification")
                result.processing_time_ms = (time.time() - start_time) * 1000
                result.all_providers_used = list(providers_used)
                result.errors = errors
                return result

            # STEP 4: CURRENCY DETECTION
            logger.debug(f"[{request_id}] [4/5] Detecting currency...")
            try:
                currency_obj = result.currency = await self._step_detect_currency(query)
                providers_used.add(currency_obj.provider)
                
                if currency_obj.currency:
                    logger.info(
                        f"[{request_id}] Currency detected: {currency_obj.currency} "
                        f"(confidence: {currency_obj.confidence:.2f})"
                    )
            except Exception as e:
                logger.error(f"[{request_id}] Currency detection failed: {e}")
                errors.append(f"currency_error: {e}")

            # STEP 5: QUERY REWRITING (CONDITIONAL)
            is_ambiguous = self._is_query_ambiguous(query, session_context, result.intent.intent)
            if is_ambiguous or result.intent.intent not in self.config.skip_rewrite_for_intents:
                logger.debug(f"[{request_id}] [5/5] Rewriting query...")
                try:
                    rewrite_obj = result.rewrite = await self._step_rewrite_query(
                        query=query,
                        intent=result.intent.intent,
                        session_context=session_context,
                    )
                    providers_used.add(rewrite_obj.provider)
                    
                    if rewrite_obj.was_rewritten:
                        logger.info(f"[{request_id}] Query rewritten: {rewrite_obj.rewritten_query[:80]}")
                except Exception as e:
                    logger.error(f"[{request_id}] Query rewriting failed: {e}")
                    errors.append(f"rewrite_error: {e}")
            else:
                logger.debug(
                    f"[{request_id}] Skipping rewrite for intent: {result.intent.intent}"
                )

        except Exception as e:
            logger.error(f"[{request_id}] Unexpected error in pipeline: {e}")
            errors.append(f"pipeline_error: {e}")

        result.processing_time_ms = (time.time() - start_time) * 1000
        result.all_providers_used = list(providers_used)
        result.errors = errors

        logger.info(
            f"[{request_id}] First layer pipeline completed in {result.processing_time_ms:.1f}ms "
            f"| Intent: {result.intent.intent} | Needs clarification: {result.needs_clarification}"
        )

        return result

    async def _step_validate(self, query: str) -> ValidationResult:
        """Step 1: Validate input."""
        try:
            is_valid, reason = await self.validator_service.validate_input_async(query)
            status = ValidationStatus.VALID if is_valid else ValidationStatus.INVALID
            return ValidationResult(status=status, reason=reason)
        except Exception as e:
            logger.warning(f"Validation fallback to sync: {e}")
            is_valid, reason = self.validator_service.validate_input(query)
            status = ValidationStatus.VALID if is_valid else ValidationStatus.INVALID
            return ValidationResult(status=status, reason=reason)

    async def _step_detect_intent(self, query: str) -> IntentResult:
        """Step 2: Detect intent using configured service."""
        intent_obj, confidence, reasoning = self.intent_service.detect_intent(query)
        return IntentResult(
            intent=intent_obj.value,
            confidence=confidence,
            reasoning=reasoning,
            provider="gemini",  # Primary provider
        )

    async def _step_check_ambiguity(
        self,
        query: str,
        intent: str,
        confidence: float,
        session_context: Optional[Any] = None,
    ) -> AmbiguityCheckResult:
        """Step 3: Check for ambiguity and generate clarification if needed."""
        # Rule-based ambiguity check
        should_ask = False
        trigger_reason = None
        clarification_q = None
        candidates = []

        # Rule: Low confidence or followup fragment on Turn 2+
        is_turn_2_plus = session_context and len(getattr(session_context, 'turns', [])) > 0
        q_lower = query.lower().strip()
        is_followup = is_turn_2_plus and any(q_lower.startswith(prefix) for prefix in RELATIVE_PREFIXES)

        if confidence < self.config.ambiguity_confidence_threshold or is_followup:
            should_ask = True
            trigger_reason = "followup_fragment" if is_followup else "low_confidence"

        if should_ask:
            # Generate clarification question using ask_back service
            try:
                ask_back_result = await self.ask_back_service.get_clarification_async(
                    query=query,
                    intent_label=intent,
                    confidence=confidence,
                    session=session_context,
                )
                clarification_q = ask_back_result.question
                candidates = ask_back_result.candidate_intents
            except Exception as e:
                logger.warning(f"Ask-back service failed: {e}, using template fallback")
                clarification_q = f"I'm not entirely sure if you're asking about {intent}. Could you clarify?"
                candidates = [intent]

        return AmbiguityCheckResult(
            should_ask_back=should_ask,
            trigger_reason=trigger_reason,
            clarification_question=clarification_q,
            candidate_intents=candidates,
            provider="rule_based",
        )

    async def _step_detect_currency(self, query: str) -> CurrencyResult:
        """Step 4: Detect currency from query."""
        try:
            currency, confidence, reasoning = self.currency_service.detect_currency(query)
            return CurrencyResult(
                currency=currency,
                confidence=confidence,
                reasoning=reasoning,
                provider="minilm",
            )
        except Exception as e:
            logger.warning(f"Currency detection failed: {e}")
            return CurrencyResult(provider="minilm")

    def _is_query_ambiguous(self, query: str, session_context: Optional[Any], intent: str) -> bool:
        """
        Evaluate if the incoming query is ambiguous/context-dependent
        (containing fragments, elliptical follow-ups, relative references, or missing required slots).
        """
        if not session_context or not getattr(session_context, "turns", None):
            # Turn 1: No history, cannot refer back to anything, so it stands on its own.
            return False

        q_lower = query.lower().strip()
        
        # 1. Rule-based: check for explicit relative pronouns / context-dependent words
        relative_words = [
            r"\bit\b", r"\bthat\b", r"\bthis\b", r"\bthose\b", r"\bthey\b", r"\bthem\b",
            r"\bits\b", r"\bthere\b", r"\bhere\b", r"\bprevious\b", r"\babove\b", r"\bsame\b"
        ]
        if any(re.search(pattern, q_lower) for pattern in relative_words):
            logger.debug(f"[RewriteGate] Ambiguous: Contains relative words in query '{query}'")
            return True

        # 2. Rule-based: check for conversational relative phrases / follow-ups
        if any(q_lower.startswith(prefix) for prefix in RELATIVE_PREFIXES):
            logger.debug(f"[RewriteGate] Ambiguous: Starts with relative prefix in query '{query}'")
            return True

        # 3. Short fragment/ellipses check on subsequent turns
        words = q_lower.split()
        if len(words) <= 3:
            logger.debug(f"[RewriteGate] Ambiguous: Short query fragment ({len(words)} words) on turn 2+ in query '{query}'")
            return True

        # 4. Slot-based completeness check:
        # If the query itself is missing crucial slots for the detected intent (e.g. product category),
        # but those slots are present in the session context, then it's context-dependent.
        from ..services.input_rewriter import extract_context_updates, REQUIRED_FIELDS_BY_INTENT
        query_slots = extract_context_updates(query)
        
        if intent in REQUIRED_FIELDS_BY_INTENT:
            required = REQUIRED_FIELDS_BY_INTENT[intent]
            # Check if any required field is missing in the raw query, but present in the context
            for field in required:
                if not query_slots.get(field) and getattr(session_context, field, None):
                    logger.debug(f"[RewriteGate] Ambiguous: Missing required slot '{field}' in query, but present in context")
                    return True

        return False

    def _classify_query_noise(self, query: str) -> Optional[str]:
        """Classify if the query contains lexical (filler) or semantic (narrative) noise."""
        words = query.lower().split()
        if len(words) < 10:
            return None  # Too short for noise to matter
        
        # 1. Semantic narrative noise check (higher precedence, threshold >= 10 words)
        if any(re.search(pat, query.lower()) for pat in NARRATIVE_PATTERNS):
            return "semantic"
        
        # 2. Lexical filler noise check
        filler_count = sum(1 for pat in FILLER_PATTERNS if re.search(pat, query.lower()))
        if (filler_count / len(words)) > 0.15:
            return "lexical"
                
        return None

    def _strip_noise_local(self, query: str) -> str:
        """Preserve query intact without destructive regex word deletion."""
        return query.strip()

    async def _step_rewrite_query(
        self,
        query: str,
        intent: str,
        session_context: Optional[Any] = None,
    ) -> RewriteResult:
        """Step 5: Rewrite query using configured provider."""
        # 1. Ambiguity-Based Gating Check
        is_ambiguous = self._is_query_ambiguous(query, session_context, intent)
        
        # 2. If it is NOT ambiguous, check if we need to clean up noise
        if not is_ambiguous:
            noise_type = self._classify_query_noise(query)
            
            if noise_type == "lexical":
                cleaned = self._strip_noise_local(query)
                logger.info(f"bypassed rewrite (full intent), but stripped lexical noise locally: '{query}' -> '{cleaned}'")
                return RewriteResult(
                    original_query=query,
                    rewritten_query=cleaned,
                    was_rewritten=cleaned != query,
                    reason="noise_stripped_local",
                    provider="gate",
                )
            elif noise_type == "semantic":
                logger.info("verbose narrative query detected, falling through to use Gemini rewritten query")
                # Fall through to rewriter_service
                pass
            else:
                logger.info("bypassed rewrite (full intent)")
                return RewriteResult(
                    original_query=query,
                    rewritten_query=query,
                    was_rewritten=False,
                    reason="bypassed_rewrite_full_intent",
                    provider="gate",
                )

        logger.info("rewriting ambiguous/verbose query using rolling summary")
        try:
            rewritten, metadata = await self.rewriter_service.rewrite_input(
                user_input=query,
                context=session_context,
                intent_hint=intent,
            )
            was_rewritten = rewritten != query
            return RewriteResult(
                original_query=query,
                rewritten_query=rewritten,
                was_rewritten=was_rewritten,
                reason=metadata.get("rewrite_reason", "") if is_ambiguous else "semantic_noise_stripped",
                provider="gemini",
            )
        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}")
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                was_rewritten=False,
                reason=str(e),
                provider="gemini",
            )


# Module-level singleton
_instance: Optional["LLMFirstLayerService"] = None


class LLMFirstLayerService:
    """
    High-level façade over FirstLayerPipeline.

    Provides both async (process) and sync (detect_intent / detect_currency)
    interfaces so it can be used from legacy synchronous callers as well as modern async code.
    """

    def __init__(self, config: Optional[LLMFirstLayerConfig] = None):
        self.config = config or LLMFirstLayerConfig()
        self._pipeline = FirstLayerPipeline(self.config)
        
        # Initialize session manager
        from ..services.session_context import SessionManager
        self.session_manager = SessionManager()

    @property
    def ask_back_service(self):
        return self._pipeline.ask_back_service

    async def get_clarification_async(self, *args, **kwargs):
        return await self._pipeline.ask_back_service.get_clarification_async(*args, **kwargs)

    def resolve_from_user_response(self, user_text: str, candidate_intents: list) -> Optional[str]:
        return self._pipeline.ask_back_service.resolve_from_user_response(user_text, candidate_intents)

    def get_or_create_session(self, session_id: str) -> Any:
        """Retrieve or create session context for a session ID."""
        return self.session_manager.get_or_create_session(session_id)

    def get_session_readonly(self, session_id: str) -> Optional[Any]:
        """Retrieve session context read-only without creating it if it doesn't exist."""
        return self.session_manager.get_session_readonly(session_id)

    def update_session_context(self, session_id: str, **kwargs: Any) -> None:
        """Update session context attributes."""
        self.session_manager.update_session_context(session_id, **kwargs)

    def _get_llm_service(self):
        """Helper to get/create LLM service with first layer config."""
        from ..core.config import LLMServiceConfig
        from ..ai.model_client import get_llm_service
        from ..ai import model_client as llm_service_mod
        
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
            existing_intent_provider = getattr(existing.config, "intent_provider", "")
            existing_api_key = getattr(existing.config, "gemini_api_key", None)
            if existing_intent_provider != self.config.intent_provider:
                llm_service_mod._llm_service_instance = None
            elif not existing_api_key and self.config.gemini_api_key:
                llm_service_mod._llm_service_instance = None

        return get_llm_service(llm_config)

    def _normalize_key(self, query: str) -> str:
        """Standardize the query key for cache lookup."""
        if not query:
            return ""
        return query.lower().strip()

    def get_request_unified_result(self) -> Optional[Dict[str, Any]]:
        """Retrieve the request-scoped unified result, if any."""
        return unified_result_var.get()

    def reset_request_unified_result(self) -> None:
        """Clear the request-scoped unified result context variable."""
        unified_result_var.set(None)

    async def get_unified_result(self, query: str, session_context: Optional[Any] = None) -> Dict[str, Any]:
        """Runs validation, intent classification, and query rewriting in a single request."""
        normalized_q = self._normalize_key(query)
        cached = unified_result_var.get()
        if cached and self._normalize_key(cached.get("query", "")) == normalized_q:
            # Update query key to match current request so downstream exact lookups match
            cached["query"] = query
            return cached

        history_str = ""
        context_str = ""
        rolling_summary_str = ""
        
        if session_context:
            if hasattr(session_context, "turns") and session_context.turns:
                history_str = "\nConversation History:\n"
                for turn in session_context.turns[-3:]:
                    user_val = turn.get("user") or turn.get("user_input", "")
                    bot_val = turn.get("bot") or turn.get("bot_response", "")
                    history_str += f"User: {user_val}\nAssistant: {bot_val}\n"
            
            parts = []
            if getattr(session_context, "product_category", None):
                parts.append(f"- Product Category: {session_context.product_category}")
            if getattr(session_context, "commercial_description", None):
                parts.append(f"- Commercial Description: {session_context.commercial_description}")
            if getattr(session_context, "last_entity", None):
                parts.append(f"- Last Entity: {session_context.last_entity}")
            if getattr(session_context, "import_export_mode", None):
                parts.append(f"- Import/Export Mode: {session_context.import_export_mode}")
            if getattr(session_context, "origin_country", None):
                parts.append(f"- Origin Country: {session_context.origin_country}")
            if getattr(session_context, "destination_country", None):
                parts.append(f"- Destination Country: {session_context.destination_country}")
            if getattr(session_context, "hs_code", None):
                parts.append(f"- HS Code: {session_context.hs_code}")
            if getattr(session_context, "cif_value", None):
                parts.append(f"- CIF Value: {session_context.cif_value}")
            if getattr(session_context, "currency", None):
                parts.append(f"- Currency: {session_context.currency}")
            if getattr(session_context, "year", None):
                parts.append(f"- Year: {session_context.year}")
            if getattr(session_context, "month", None):
                parts.append(f"- Month: {session_context.month}")
            if getattr(session_context, "trade_agreement", None):
                parts.append(f"- Trade Agreement: {session_context.trade_agreement}")
            if parts:
                context_str = "\nActive Session Context:\n" + "\n".join(parts) + "\n"
                
            rolling_summary_str = getattr(session_context, "rolling_summary", "")

        llm_service = self._get_llm_service()
        if hasattr(llm_service, "unified_first_layer_call"):
            res = await llm_service.unified_first_layer_call(
                query=query,
                history=history_str,
                rolling_summary=rolling_summary_str,
                context_str=context_str
            )
            if res:
                res["query"] = query
                unified_result_var.set(res)
                return res
        return {}

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
        prompt_name: str = "gemini_unified_first_layer",
    ) -> Tuple[str, Dict[str, Any]]:
        """Compatibility wrapper for legacy rewrite_input callers."""
        # Try to use unified cache results if available.
        # IMPORTANT: skip the cache when the caller requests a non-unified prompt
        # (e.g. "gemini_rewrite_input" for post-clarification rewrites where intent is
        # already locked). The pre-warm in endpoints.py always runs the full unified layer,
        # so its cached result is wrong to reuse for lightweight-only calls.
        cached = unified_result_var.get()
        if (
            prompt_name == "gemini_unified_first_layer"
            and cached
            and self._normalize_key(cached.get("query", "")) == self._normalize_key(user_input)
        ):
            rewritten = cached.get("rewritten_query")
            if rewritten:
                rewritten = rewritten.strip()
                was_rewritten = rewritten != user_input
                logger.info(f"Reusing unified cache rewritten query: '{rewritten}'")
                return rewritten, {
                    "rewrite_reason": "unified_rewrite",
                    "confidence": 0.8,
                    "intent_changed": was_rewritten,
                    "topic_switch": False,
                    "rewritten": was_rewritten,
                }
        elif prompt_name != "gemini_unified_first_layer" and cached:
            logger.info(
                f"[REWRITE] Cache bypass: prompt_name='{prompt_name}' requested; "
                f"skipping pre-warm unified cache hit and calling LLM directly."
            )

        llm_service = self._get_llm_service()
        return await llm_service.rewrite_input(
            user_input=user_input,
            context=context,
            intent_hint=intent_hint,
            prompt_name=prompt_name,
        )

    # Primary async API

    async def process(
        self,
        query: str,
        request_id: str,
        session_context: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> FirstLayerResult:
        """[DEPRECATED] Run the full first-layer pipeline and return a FirstLayerResult."""
        import warnings
        warnings.warn(
            "LLMFirstLayerService.process is deprecated and unused in production. Use get_unified_result instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return await self._pipeline.process(
            query=query,
            request_id=request_id,
            session_context=session_context,
            session_id=session_id,
        )

    # Synchronous shim helpers (used by legacy / sync callers)

    def detect_intent(
        self,
        query: str,
        session_context: Optional[Any] = None,
        request_id: str = "sync",
    ) -> Tuple[Any, float, str]:
        """
        Synchronous intent detection.

        Returns (intent_value, confidence, reasoning) matching the tuple
        shape expected by OllamaProvider and other legacy consumers.
        """
        result = self._run_sync(
            self.process(
                query=query,
                request_id=request_id,
                session_context=session_context,
            )
        )
        intent = result.intent
        # Return a simple object with .value so callers doing `intent.value` work
        class _IntentValue:
            def __init__(self, v: str):
                self.value = v
            def __str__(self):
                return self.value

        return _IntentValue(intent.intent), intent.confidence, intent.reasoning

    # Internal helpers

    @staticmethod
    def _run_sync(coro) -> Any:
        """Run a coroutine synchronously, creating an event loop if needed."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already inside an async context, schedule and wait
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)


def get_llm_first_layer_service(
    config: Optional[LLMFirstLayerConfig] = None,
) -> LLMFirstLayerService:
    """
    Return the module-level singleton LLMFirstLayerService.

    If *config* is provided on the first call it is used to initialise the
    instance; subsequent calls ignore *config* and return the existing singleton.
    """
    global _instance
    if _instance is None:
        _instance = LLMFirstLayerService(config)
    return _instance


class LLMAskBackService:
    def __init__(self, pipeline: "FirstLayerPipeline"):
        self.pipeline = pipeline

    async def get_clarification_async(
        self,
        query: str,
        intent_label: str,
        confidence: float,
        session: Optional[Any] = None,
        candidate_scores: Optional[dict] = None,
        turn_number: int = 1,
    ) -> Any:
        """
        Generates dynamic clarification questions using LLM and dynamic prompts loaded via DynamicPromptManager.
        Falls back to intent-level fallback questions if LLM generation is unavailable.
        """
        candidates = [intent_label]

        # 1. Prepare session history context if available
        history_str = ""
        if session and hasattr(session, "turns") and session.turns:
            history_str = "\n".join(
                f"User: {t.get('user') or t.get('user_input', '')}\nAssistant: {t.get('bot') or t.get('bot_response', '')}"
                for t in session.turns[-2:]
            )

        # 2. Baseline fallback question (ensures question is always defined even if LLM call fails)
        fallback_map = {
            "hs_code_lookup": "Of course! I can help you with HS code classification. What product are you trying to look up?",
            "calculation": "Sure! I can help you estimate customs duties and taxes. What product are you importing, and what is its CIF value or import details?",
            "trade_query": "Happy to help with trade statistics. Could you please specify the product or commodity and time period (e.g. Q1 2026 or last year)?",
        }
        question = fallback_map.get(
            intent_label,
            f"I want to make sure I assist you correctly. Are you looking to find an HS code, calculate import duties/taxes, check trade statistics, or something else?"
        )

        # 3. Dynamic LLM generation using prompt managed via DynamicPromptManager
        llm_service = None
        if hasattr(self.pipeline, "intent_service") and self.pipeline.intent_service:
            llm_service = getattr(self.pipeline.intent_service, "_llm_provider", None)

        if not llm_service:
            from ..ai import get_llm_service
            llm_service = get_llm_service()

        if llm_service and hasattr(llm_service, "router") and llm_service.is_available():
            prompt = _prompt_manager.render(
                "ask_back_ambiguous_intent",
                query=query,
                intent_label=intent_label,
                confidence=f"{confidence:.2f}",
                history=history_str if history_str else "None",
            )
            try:
                provider = llm_service.router.providers.get("gemini")
                if provider and provider.is_available():
                    response = await asyncio.to_thread(
                        provider.client.models.generate_content,
                        model=provider.model_name,
                        contents=prompt,
                    )
                    content = (response.text or "").strip()
                    if content:
                        question = content
            except Exception as e:
                logger.warning(f"Failed to generate dynamic LLM clarification question: {e}")

        class AskBackResult:
            def __init__(self, should_ask_back: bool, question: str, candidate_intents: list):
                self.should_ask_back = should_ask_back
                self.question = question
                self.candidate_intents = candidate_intents
                self.trigger_reason = "low_confidence_or_ambiguous"

        return AskBackResult(should_ask_back=True, question=question, candidate_intents=candidates)

    def resolve_from_user_response(self, user_text: str, candidate_intents: list) -> Optional[str]:
        """
        Synchronously resolves which candidate intent the user selected.
        If there is only one candidate, resolves to it unless the user explicitly requested a different intent.
        """
        if not candidate_intents:
            return None

        low_text = (user_text or "").lower().strip()

        # Check if user explicitly requested a DIFFERENT core intent than what is in candidate_intents
        has_other_hs = any(re.search(rf"\b{re.escape(w)}\b", low_text) for w in ["hs", "tariff", "hs code", "hs-code", "hscode", "tariff code", "ahtn", "hs classification", "tariff classification"])
        has_other_calc = any(re.search(rf"\b{re.escape(w)}\b", low_text) for w in ["calculate duty", "calculate tax", "compute duty", "calculate import", "duty calculation", "calc duty", "calc tax", "calculate"])
        has_other_trade = any(re.search(rf"\b{re.escape(w)}\b", low_text) for w in ["trade data", "trade statistics", "trade volume", "trade flow", "import statistics", "export statistics"])

        # Robust calculation signal: calculation verbs/nouns or monetary/numeric patterns (e.g. "$20", "5 units", "cif", "tax", "duty")
        has_calc_signal = (
            any(re.search(rf"\b{re.escape(w)}\b", low_text) for w in [
                "calculate", "calc", "compute", "duty", "tax", "vat", "cif", "fob",
                "value", "cost", "price", "fee", "rate", "amount", "total"
            ])
            or bool(re.search(r"[$€£¥₩]\s*\d+|\d+\s*[$€£¥₩]|\b\d+\b", low_text))
        )

        # Counter-signal: if query contains ANY calculation signal, HS code number, or corrective reply phrase AND calculation is an eligible candidate,
        # suppress has_other_hs so that supplying an HS code slot for calculation is not treated as a topic switch to hs_code_lookup.
        has_hs_number = bool(re.search(r"\b\d{4}\.\d{2}(?:\.\d{2})?\b|\b\d{8}\b", low_text))
        is_corrective_hs_reply = "correct" in low_text or "right" in low_text or "use" in low_text
        is_explicit_hs_lookup_ask = any(phrase in low_text for phrase in ["what is the hs code", "find hs code", "lookup hs code", "search hs code"])
        if (has_calc_signal or has_hs_number or is_corrective_hs_reply) and "calculation" in candidate_intents and not is_explicit_hs_lookup_ask:
            has_other_hs = False

        if has_other_hs and "hs_code_lookup" not in candidate_intents:
            return None
        if has_other_calc and "calculation" not in candidate_intents:
            return None
        if has_other_trade and "trade_query" not in candidate_intents:
            return None

        if len(candidate_intents) == 1:
            return candidate_intents[0]

        if has_hs_number and "calculation" in candidate_intents:
            return "calculation"

        # Simple rule-based resolution
        # Check for hs lookup keywords
        hs_kws = ["hs", "lookup", "tariff", "classify", "code", "first", "1"]
        calc_kws = ["calculate", "calculation", "tax", "duty", "fee", "second", "2"]
        trade_kws = ["trade", "stat", "volume", "third", "3"]
        general_kws = ["general", "policy", "rule", "document", "fourth", "4"]
        
        if any(w in low_text for w in hs_kws) and "hs_code_lookup" in candidate_intents:
            return "hs_code_lookup"
        if any(w in low_text for w in calc_kws) and "calculation" in candidate_intents:
            return "calculation"
        if any(w in low_text for w in trade_kws) and "trade_query" in candidate_intents:
            return "trade_query"
        if any(w in low_text for w in general_kws) and "general" in candidate_intents:
            return "general"
            
        # Default fallback to first candidate if no keyword matches
        return candidate_intents[0]
