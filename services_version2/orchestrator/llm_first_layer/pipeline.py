"""
Pipeline orchestrating the unified first LLM layer.

Coordinates validation, intent detection, ambiguity checking, 
currency detection, and query rewriting in a single unified flow.
"""

import asyncio
import logging
import time
from typing import Optional, Any

from .models import (
    FirstLayerResult,
    ValidationResult,
    ValidationStatus,
    IntentResult,
    AmbiguityCheckResult,
    CurrencyResult,
    RewriteResult,
)
from .config import LLMFirstLayerConfig

logger = logging.getLogger(__name__)


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
            from ..llm_first_layer.shims.validator_service import get_input_validator
            self._validator_service = get_input_validator()
        return self._validator_service

    @property
    def intent_service(self):
        """Lazy load intent service."""
        if self._intent_service is None:
            from ..llm_first_layer.shims.intent_service import get_intent_service, IntentServiceConfig
            config = IntentServiceConfig(
                provider=self.config.intent_provider,
                gemini_api_key=self.config.gemini_api_key,
                gemini_model=self.config.gemini_model,
                timeout=self.config.intent_timeout,
            )
            self._intent_service = get_intent_service(config)
        return self._intent_service

    @property
    def ask_back_service(self):
        """Lazy load ask back service."""
        if self._ask_back_service is None:
            try:
                from ..ask_back_service import get_ask_back_service
            except Exception:
                from ..llm_first_layer import get_llm_first_layer_service as get_ask_back_service
            self._ask_back_service = get_ask_back_service()
        return self._ask_back_service

    @property
    def currency_service(self):
        """Lazy load currency service."""
        if self._currency_service is None:
            try:
                from ..currency_service import get_currency_service, CurrencyServiceConfig
                config = CurrencyServiceConfig(
                    provider=self.config.currency_provider,
                    minilm_confidence_threshold=self.config.minilm_confidence_threshold,
                )
                self._currency_service = get_currency_service(config)
            except Exception:
                from ..llm_first_layer import get_llm_first_layer_service as get_currency_service
                self._currency_service = get_currency_service()
        return self._currency_service

    @property
    def rewriter_service(self):
        """Lazy load rewriter service."""
        if self._rewriter_service is None:
            from ..llm_first_layer.shims.rewriter_service import get_rewriter_service, RewriterServiceConfig
            config = RewriterServiceConfig(
                rewrite_provider=self.config.rewrite_provider,
                gemini_api_key=self.config.gemini_api_key,
                gemini_model=self.config.gemini_model,
                gemini_timeout=self.config.rewrite_timeout,
            )
            self._rewriter_service = get_rewriter_service(config)
        return self._rewriter_service

    async def process(
        self,
        query: str,
        request_id: str,
        session_context: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> FirstLayerResult:
        """
        Execute the unified first LLM layer pipeline.
        
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
            # ===== STEP 1: INPUT VALIDATION =====
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

            # ===== STEP 2: INTENT DETECTION =====
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

            # ===== STEP 3: AMBIGUITY CHECK =====
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

            # ===== STEP 4: CURRENCY DETECTION =====
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

            # ===== STEP 5: QUERY REWRITING (CONDITIONAL) =====
            if result.intent.intent not in self.config.skip_rewrite_for_intents:
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

        # Rule: Low confidence
        if confidence < self.config.ambiguity_confidence_threshold:
            should_ask = True
            trigger_reason = "low_confidence"

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

    async def _step_rewrite_query(
        self,
        query: str,
        intent: str,
        session_context: Optional[Any] = None,
    ) -> RewriteResult:
        """Step 5: Rewrite query using configured provider."""
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
                reason=metadata.get("rewrite_reason", ""),
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
