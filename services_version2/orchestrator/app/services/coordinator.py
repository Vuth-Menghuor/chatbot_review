"""
Coordinator Module - Orchestrator service
Coordinates requests across multiple backend services
Includes input rewriting layer for context-aware processing
Supports intent-specific timeout management (STEP 4)
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
import uuid
import re
from datetime import datetime, timezone

from ..utils import extract_entity, strip_clarification_questions_from_prose

from ..infrastructure.cache_service import get_cache_service
from ..ai import OrchestratorLLMService, LLMServiceConfig, get_llm_service
from ..ai.shims.intent_service import OrchestratorIntentService, IntentServiceConfig
from ..ai import get_llm_first_layer_service as get_intent_service
from ..ai.summarizer import OrchestratorFormatterService, get_formatter_service
from ..core.config import FormatterServiceConfig
from ..ai.shims.rewriter_service import RewriterService, RewriterServiceConfig, get_rewriter_service
from ..ai.analyzer import RELATIVE_PREFIXES

from prompts.dynamic_prompt_manager import DynamicPromptManager

# Module-level prompt manager — loads from prompts/ directory on import
_prompt_manager = DynamicPromptManager()

from .workflow import (
    WorkflowExecutor,
    WorkflowContext,
    WorkflowIntent,
    WorkflowStatus,
)
from .suggestion_service import SuggestionService
from ..core.config import (
    TimeoutConfig,
    get_timeout_config,
)

from ..ai.shims.validator_service import (
    extract_certificate_type,
    get_validator,
    ValidationResult,
    ValidationDecision,
)

from .hs_classifier import detect_simple_product_category

logger = logging.getLogger(__name__)

# Imported heuristics and constants
from .heuristics import (
    _TRADE_COUNTRIES,
    _NON_PRODUCT_PREFIXES,
    _CLARIFY_STOP_WORDS,
    _CLARIFY_GENERIC_NOUNS,
    _SPEC_DISCRIMINATORS,
    ALL_ESCAPE_HATCH_TERMS,
    MAX_PRODUCT_ASK_BACK_RETRIES,
    Heuristics,
)
from .clarification_manager import ClarificationManager
from .handlers.small_talk import SmallTalkHandler, generate_small_talk_response
from .handlers.definition import DefinitionHandler
from .handlers.calculation import CalculationHandler
from .handlers.trade_query import TradeQueryHandler
from .handlers.hs_lookup import HsCodeLookupHandler





async def generate_out_of_scope_refusal(query: str, llm_service=None, language: str = "en") -> str:
    """
    Generates a warm, LLM-written refusal for off-topic queries that are outside
    GDCE's operational domain (customs, trade, tax, HS codes).

    Falls back to a safe static message if the LLM is unavailable.
    The response is never cached (called only from the out-of-scope short-circuit path).
    """
    _FALLBACK = {
        "en": (
            "That's outside my area of expertise! I specialize in Cambodia customs regulations, "
            "import/export duties, HS code lookups, and trade statistics. "
            "Feel free to ask me anything related to customs or trade!"
        ),
        "km": (
            "សំណួររបស់អ្នកនៅក្រៅវិសាលភាពរបស់ខ្ញុំ! ខ្ញុំជំនាញក្នុងបទប្បញ្ញត្តិគយ "
            "ពន្ធនាំចូល/នាំចេញ ការរកលេខកូដ HS និងស្ថិតិពាណិជ្ជកម្មរបស់ប្រទេសកម្ពុជា។ "
            "សូមសួរខ្ញុំអំពីរឿងទាក់ទងនឹងគយ ឬពាណិជ្ជកម្ម!"
        ),
    }

    if llm_service and llm_service.is_available():
        lang_label = "Khmer" if language == "km" else "English"
        prompt = _prompt_manager.render(
            "generate_out_of_scope_refusal",
            query=query,
            language=lang_label,
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
                    return content
        except Exception as e:
            logger.warning(f"LLM out-of-scope refusal generation failed: {e}")

    return _FALLBACK.get(language, _FALLBACK["en"])


async def detect_small_talk(query: str, llm_service=None, force_llm_fallback: bool = False) -> Optional[str]:

    """Detects if the query is small talk/casual/unrelated and provides a friendly response."""
    # To avoid classification logic duplication, if force_llm_fallback=True (meaning we know it's small talk),
    # we directly call the generation helper.
    if force_llm_fallback:
        return await generate_small_talk_response(query, llm_service)
        
    # Otherwise, perform keyword/regex check
    res = await generate_small_talk_response(query, llm_service=None)
    # If it was an obvious static category response, return it
    if res and not res.startswith("Hello! I'm here to help"):
        return res
        
    # If llm_service is provided and not force_llm_fallback, check if it is small talk
    if llm_service and llm_service.is_available():
        prompt = _prompt_manager.render("detect_small_talk", query=query)
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
                    if content.upper() == "FALSE" or "FALSE" in content.upper()[:10]:
                        return None
                    return content
        except Exception as e:
            logger.warning(f"LLM small talk classification check failed: {e}")
            
    return None


class ServiceCoordinator:
    """Coordinates requests across retrieval, calculation, and trade data services."""
    
    def __init__(
        self,
        retrieval_client=None,
        general_client=None,
        calculator_client=None,
        trade_data_client=None,
        policy_engine=None,
        use_llm_intent: bool = True,
        llm_intent_timeout: int = 60,
        use_input_rewriter: bool = True,
        timeout_config: Optional[TimeoutConfig] = None,
        gemini_api_key: Optional[str] = None,
        llm_service: Optional[OrchestratorLLMService] = None,
        intent_service: Optional[OrchestratorIntentService] = None,
        formatter_service: Optional[OrchestratorFormatterService] = None,
        rewriter_service: Optional[RewriterService] = None,
        first_layer_service: Optional[Any] = None,
        suggestion_service: Optional[SuggestionService] = None,
    ):
        self.retrieval_client = retrieval_client
        self.general_client = general_client or retrieval_client
        self.calculator_client = calculator_client
        self.trade_data_client = trade_data_client
        self.first_layer_service = first_layer_service  
        self.suggestion_service = suggestion_service or SuggestionService()
        
        self.llm_service = llm_service or get_llm_service(
            LLMServiceConfig(
                intent_provider="gemini",
                rewrite_provider="gemini",
                summarization_provider="gemini",
                hs_selection_provider="gemini",
                gemini_api_key=gemini_api_key,
            )
        )
        
        self.intent_service = intent_service or get_intent_service(
            IntentServiceConfig(provider="gemini", gemini_api_key=gemini_api_key)
        )
        
        self.formatter_service = formatter_service or get_formatter_service(
            FormatterServiceConfig(provider="gemini", gemini_api_key=gemini_api_key, enabled=True)
        )
        
        self.rewriter_service = rewriter_service or (llm_service if llm_service and hasattr(llm_service, "rewrite_input") else get_rewriter_service(
            RewriterServiceConfig(rewrite_provider="gemini", gemini_api_key=gemini_api_key)
        ))
        
        self.workflow_executor = WorkflowExecutor(
            policy_engine,
            use_llm_intent=use_llm_intent,
            llm_intent_timeout=llm_intent_timeout,
            llm_service=self.llm_service,
        )
        from .translator import QueryTranslator
        self.query_translator = QueryTranslator(self.llm_service)
        self.policy_engine = policy_engine
        self.timeout_config = timeout_config or get_timeout_config()
        self.use_input_rewriter = use_input_rewriter
        logger.info(f" LLM abstraction layer initialized (input rewrite enabled: {use_input_rewriter})")

    async def _detect_small_talk(self, query: str, llm_service=None, force_llm_fallback: bool = False) -> Optional[str]:
        return await detect_small_talk(query, llm_service, force_llm_fallback)

    def _normalize_turn2_input(self, text: str) -> str:
        return Heuristics.normalize_turn2_input(text)

    def _is_turn2_escape_hatch(self, text: str) -> bool:
        return Heuristics.is_turn2_escape_hatch(text)

    def _is_vague_trade_query(self, query: str) -> bool:
        return Heuristics.is_vague_trade_query(query)
    
    
    async def process_query(
        self,
        question: str,
        session_id: Optional[str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Public entrypoint for query processing. Detects and handles translation if the query is in Khmer.

        When stream=True the coordinator skips the synchronous formatter and
        returns a raw WorkflowContext-shaped dict so the streaming endpoint can
        own the final text-generation step.
        """
        from .translator import QueryTranslator
        translator = QueryTranslator(self.llm_service)
        is_km = translator.is_khmer(question)
        original_question = question

        if is_km:
            try:
                english_question = await translator.translate_to_english(question)
                logger.info(f"Translated Khmer query '{question}' to English '{english_question}'")
                question = english_question
            except Exception as e:
                logger.error(f"Failed to translate Khmer query to English: {e}")

        response = await self._process_query_core(
            question=question,
            session_id=session_id,
            is_km=is_km,
            original_question=original_question,
            stream=stream,
        )

        # For streaming mode, Khmer translation is handled by the endpoint after
        # the stream completes so we skip it here.
        target_lang = response.get("metadata", {}).get("language")
        if not target_lang and hasattr(response.get("context"), "session_context"):
            target_lang = getattr(response["context"].session_context, "target_language", "en")

        if not stream and (is_km or target_lang == "km"):
            if "metadata" not in response:
                response["metadata"] = {}
            response["metadata"]["language"] = "km"

            text_key = "answer"
            if "error" in response and not response.get("answer"):
                text_key = "error"

            english_text = response.get(text_key)
            if english_text and isinstance(english_text, str) and english_text.strip():
                if not translator.is_khmer(english_text):
                    try:
                        khmer_text = await translator.translate_to_khmer(english_text)
                        logger.info(f"Translated English response '{english_text[:100]}...' to Khmer '{khmer_text[:100]}...'")
                        response[text_key] = khmer_text
                    except Exception as e:
                        logger.error(f"Failed to translate response to Khmer: {e}")

        return response

    async def _process_query_core(
        self,
        question: str,
        session_id: Optional[str] = None,
        is_km: bool = False,
        original_question: Optional[str] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Processes an incoming user query through the orchestration pipeline.

        When stream=True downstream service calls use generate_answer=False so
        that raw documents/data are returned without the service running its own
        LLM formatting step.  The coordinator then returns a context dict that
        the streaming endpoint uses to build the Gemini prompt.

        The execution flow is as follows:
        1. Context initialization & tracking.
        2. Query normalization & fast small-talk detection.
        3. Input validation & safety/scope boundary checks.
        4. Clarification resolution if the session was awaiting user input.
        5. Intent detection & core intent filtering.
        6. Proactive ask-back checks for ambiguous core queries.
        7. Context-aware input rewriting using session history.
        8. Microservice routing & dispatching (calculator, trade_data, retrieval).
        9. Session state updates (session save deferred to endpoint in stream mode).
        """
        # Step 1: Initialize a unique request ID and workflow tracking context
        request_id = str(uuid.uuid4())
        context = WorkflowContext(
            request_id=request_id,
            question=question,
            session_id=session_id,
            original_input=question  
        )
        if is_km:
            context.metadata["detected_language"] = "km"
            context.metadata["original_question"] = original_question

         
        try:
            # Step 2: Perform light normalization (lowercase, stripping) for early classification matching
            normalized_question = self._light_normalize_query(question)
            context.metadata["normalized_input"] = normalized_question
            
            # Load session history context early if session tracking and rewriter are enabled
            if self.use_input_rewriter and session_id:
                try:
                    session_context = self.rewriter_service.get_or_create_session(session_id)
                    context.session_context = session_context
                except Exception as e:
                    logger.warning(f"[{request_id}] Session context unavailable: {e}")

            # Step 2c: Product-spec clarification merge.
            # When retrieval previously flagged a response as is_generic=True and stored
            # product_clarification_needed=True on the session, the next user message is
            # (likely) a spec answer to that clarification question.  We try to merge it
            # with the saved entity before any other processing so the rest of the pipeline
            # sees the full, self-contained query (e.g. "bmw m8 competition sports car").
            # Mutual-exclusion: skip if the session is already in intent ask-back mode.
            if (
                context.session_context
                and getattr(context.session_context, "product_clarification_needed", False)
                and not context.session_context.is_awaiting_clarification()
            ):
                question, normalized_question = await self._try_merge_product_spec(
                    context=context,
                    request_id=request_id,
                    question=question,
                    normalized_question=normalized_question,
                    session_id=session_id,
                )

            # Ghost Step 2b for spec check: if not has_history or context.metadata.get("_spec_merge_done")
            # Step 3: Fast-path check for predefined/casual small talk (greetings, gratitude, etc.)
            if context.metadata.get("small_talk_response"):
                context.intent = WorkflowIntent.SMALL_TALK
                context.skip_intent_detection = True

            # Step 4: Clean up query (stripping excessive punctuation/whitespaces) for internal processing
            cleaned_question = self.workflow_executor.cleanup_query(question)
            original_query = cleaned_question
            context.cleaned_input = original_query

            # Step 7: Clarification Resolution (Handling user reply to a previous ask-back question)
            if context.session_context and context.session_context.is_awaiting_clarification():
                try:
                    from ..ai import get_llm_first_layer_service as get_ask_back_service
                    ask_back_svc = get_ask_back_service()
                    
                    # Fetch unified NLU cache to check if the user shifted topic/greetings
                    cache_intent = None
                    cache_conf = 0.0
                    if self.first_layer_service:
                        cache = self.first_layer_service.get_request_unified_result()
                        if cache:
                            norm_q = self.first_layer_service._normalize_key(normalized_question)
                            if self.first_layer_service._normalize_key(cache.get("query", "")) == norm_q:
                                cache_intent = cache.get("intent")
                                cache_conf = cache.get("confidence", 0.0)

                    # Layer 1: Deterministic structural fragment check
                    is_slot_reply = self._is_slot_fragment_reply(
                        normalized_question, context.session_context.clarification_intents
                    )

                    # Guard 1: Small talk exit check (only if NOT a slot fragment reply)
                    if not is_slot_reply and cache_intent == "small_talk":
                        logger.info(f"[{request_id}] [ASK-BACK-EXIT] Small talk detected during clarification. Exiting.")
                        context.session_context.resolve_clarification(None)
                        context.intent = WorkflowIntent.SMALL_TALK
                        small_talk_resp = await generate_small_talk_response(question, self.llm_service)
                        context.metadata["small_talk_response"] = small_talk_resp
                        context.skip_intent_detection = True

                    else:
                        # Guard 2: Topic switch / nested ask-back check
                        # Layer 1: Deterministic structural fragment check
                        is_slot_reply = self._is_slot_fragment_reply(
                            normalized_question, context.session_context.clarification_intents
                        )

                        is_topic_switch_candidate = (
                            not is_slot_reply
                            and cache_intent in {"hs_code_lookup", "calculation", "trade_query", "general"}
                            and cache_intent not in context.session_context.clarification_intents
                        )
                        is_bare_noun = False
                        if is_topic_switch_candidate:
                            # Precedence check: if it looks like a bare noun and locked intent is commodity-driven, let it merge
                            is_bare_noun = (
                                self._looks_like_short_product_lookup(normalized_question)
                                and any(intent in {"hs_code_lookup", "calculation", "trade_query"} for intent in context.session_context.clarification_intents)
                            )

                        should_exit = False
                        if is_topic_switch_candidate and not is_bare_noun:
                            if cache_conf < 0.50 or cache_intent == "small_talk":
                                logger.info(f"[{request_id}] [ASK-BACK-EXIT] Topic switch / low confidence ({cache_conf} < 0.50) to {cache_intent}. Exiting clarification.")
                                context.session_context.resolve_clarification(None)
                                self._clear_product_clarification(context.session_context)
                                should_exit = True
                            elif cache_conf >= 0.80:
                                logger.info(f"[{request_id}] [ASK-BACK-EXIT] High-confidence topic switch detected to {cache_intent} (conf={cache_conf}). Exiting clarification.")
                                context.session_context.resolve_clarification(None)
                                self._clear_product_clarification(context.session_context)
                                should_exit = True
                            elif 0.60 <= cache_conf < 0.80:
                                logger.info(f"[{request_id}] [ASK-BACK-EXIT] Nested Ask-Back triggered for {cache_intent} (conf={cache_conf}).")
                                context.session_context.resolve_clarification(None)
                                self._clear_product_clarification(context.session_context)
                                llm_ask_back = ask_back_svc.ask_back_service
                                ask_back_res = await llm_ask_back.get_clarification_async(
                                    query=question,
                                    intent_label=cache_intent,
                                    confidence=cache_conf,
                                )
                                clarification_text = ask_back_res.question
                                candidates = ask_back_res.candidate_intents
                                
                                context.session_context.pending_clarification = True
                                context.session_context.clarification_intents = candidates
                                context.session_context.pending_rewritten_query = question
                                
                                context.finalize()
                                return self._build_ask_back_response(
                                    context,
                                    question=question,
                                    clarification_question=clarification_text,
                                    candidate_intents=candidates,
                                    trigger_reason="nested_ask_back",
                                )
                            elif 0.30 <= cache_conf < 0.60:
                                logger.info(f"[{request_id}] [ASK-BACK-EXIT] Low-confidence topic switch detected to {cache_intent} (conf={cache_conf}). Exiting clarification.")
                                context.session_context.resolve_clarification(None)
                                self._clear_product_clarification(context.session_context)
                                should_exit = True
                            else:
                                logger.info(f"[{request_id}] [ASK-BACK-IGNORE] Extremely low-confidence topic switch candidate {cache_intent} (conf={cache_conf} < 0.30) treated as classifier noise; staying in clarification.")

                        if not should_exit:
                            # Check if the user reply is a pure escape-hatch (e.g. "idk", "whatever", "មិនដឹង") without an entity
                            norm_reply = self._normalize_turn2_input(question)
                            has_country_match = any(c in norm_reply for c in _TRADE_COUNTRIES)
                            if context.metadata.get("has_nlu_entity", False):
                                extracted_entity = context.metadata.get("nlu_entity")
                            else:
                                extracted_entity = extract_entity(norm_reply)
                            has_entity_signal = bool(has_country_match or extracted_entity)

                            if self._is_turn2_escape_hatch(question) and not has_entity_signal:
                                logger.info(f"[{request_id}] [ASK-BACK-ESCAPE] User replied with escape hatch phrase '{question}'. Resolving with macro trade defaults.")
                                context.session_context.resolve_clarification(None)
                                context.intent = WorkflowIntent.TRADE_QUERY
                                context.question = "top 10 import partners Cambodia 2025"
                                normalized_question = "top 10 import partners Cambodia 2025"
                                context.cleaned_input = normalized_question
                                context.skip_intent_detection = True
                                context.metadata["clarification_resolved"] = {
                                    "resolved_intent": "trade_query",
                                    "via": "escape_hatch_macro_default",
                                    "merged_query": normalized_question,
                                }
                            else:
                                # Resolve which of the candidate intents the user meant based on their response
                                resolved_intent = ask_back_svc.resolve_from_user_response(
                                    user_text=question,
                                    candidate_intents=context.session_context.clarification_intents,
                                )
                                if resolved_intent:
                                    try: locked_intent = WorkflowIntent(resolved_intent)
                                    except ValueError: locked_intent = None
                                    
                                    # Retrieve the original pending query and merge it with the new clarification details.
                                    session_last_entity = getattr(context.session_context, 'last_entity', None)
                                    was_awaiting = context.session_context.is_awaiting_clarification()
                                    pending_query = context.session_context.resolve_clarification(resolved_intent)
                                
                                    # If the pending query is missing (e.g. session was created fresh without a prior
                                    # ask-back turn), fall back to the last normalized query from the session.
                                    # This lets the merge reconstruct context (CIF, origin, entity) from Turn 1.
                                    if not pending_query and getattr(context.session_context, 'last_normalized_query', None):
                                        pending_query = context.session_context.last_normalized_query
                                        logger.info(
                                            f"[{request_id}] [MERGE] pending_rewritten_query was None; "
                                            f"falling back to last_normalized_query: '{pending_query}'"
                                        )
                                    
                                    merged_query = self._merge_pending_with_clarification(
                                        pending_query=pending_query,
                                        clarification_response=question,
                                        resolved_intent=resolved_intent,
                                        session_last_entity=session_last_entity,
                                        session_context=context.session_context,
                                        was_clarification_pending=was_awaiting,
                                    )
                                    logger.info(
                                        f"[{request_id}] [MERGE] Merged pending query '{pending_query}' with "
                                        f"clarification '{question}' (resolved intent: '{resolved_intent}') -> '{merged_query}'"
                                    )
                                    context.clarification_confidence = 0.90
                                    
                                    # Validate the merged query; if invalid, fall back to using the user's latest message only
                                    if not self._validate_merged_query(merged_query, resolved_intent):
                                        logger.warning(
                                            f"[{request_id}] [MERGE] Merged query '{merged_query}' failed validation for intent '{resolved_intent}'. "
                                            f"Falling back to latest clarification response: '{question}'"
                                        )
                                        merged_query = question
                                    
                                    # Update the context query and clean/normalize it
                                    context.question = merged_query
                                    normalized_question = self._light_normalize_query(context.question)
                                    original_query = self.workflow_executor.cleanup_query(context.question)
                                    context.cleaned_input = original_query
                                    
                                    logger.info(
                                        f"[{request_id}] [MERGE] Cleaned/rewritten merged query -> '{original_query}'"
                                    )
                                    
                                    # Set intent flags to lock the resolved intent and skip subsequent intent detection
                                    context.clarification_locked_intent = locked_intent
                                    context.skip_intent_detection = True
                                    context.intent = locked_intent
                                    
                                    context.metadata["clarification_resolved"] = {
                                        "resolved_intent": resolved_intent,
                                        "via": "keyword",
                                        "merged_query": merged_query,
                                        "original_pending_query": pending_query,
                                        "clarification_response": question,
                                        "confidence": context.clarification_confidence,
                                    }
                                else:
                                    # Clarification could not be resolved. Handle retries up to MAX_ASK_BACK_RETRIES
                                    MAX_ASK_BACK_RETRIES = 2
                                    if context.session_context.ask_back_count >= MAX_ASK_BACK_RETRIES:
                                        # Too many failed attempts: clear pending state and fall through to standard processing
                                        context.session_context.pending_clarification = False
                                        context.session_context.clarification_intents = []
                                        context.session_context.ask_back_count = 0
                                    else:
                                        # Re-prompt the user to clarify with candidates
                                        context.session_context.set_pending_clarification(
                                            candidate_intents=context.session_context.clarification_intents,
                                            rewritten_query=context.session_context.pending_rewritten_query,
                                        )
                                        context.finalize()
                                        return self._build_ask_back_response(
                                            context,
                                            question=context.session_context.pending_rewritten_query or question,
                                            clarification_question=(
                                                "I still wasn't sure which option you meant. "
                                                + ask_back_svc._template.generate(
                                                    query=question,
                                                    candidate_intents=context.session_context.clarification_intents,
                                                    session=context.session_context,
                                                )
                                            ),
                                            candidate_intents=context.session_context.clarification_intents,
                                            trigger_reason="unresolved_retry",
                                        )
                except Exception as e:
                    logger.warning(f"[{request_id}] Clarification resolution failed: {e}")

            # Step 5: Validate query formatting and check domain/safety scope boundaries
            validator = get_validator()
            validation_result = await validator.validate_input_full_async(normalized_question, context.session_context)
            if getattr(validation_result, "slots", None):
                context.metadata["layer1_slots"] = validation_result.slots
            
            # If the query fails basic validation rules (safety, injection, format), fail early
            if not validation_result.is_valid and validation_result.decision not in (ValidationDecision.OUT_OF_SCOPE, ValidationDecision.AMBIGUOUS):
                context.add_error(validation_result.reason)
                context.status = WorkflowStatus.FAILED
                context.finalize()
                return {
                    "intent": "validation_error",
                    "status": "failed",
                    "error": validation_result.reason,
                    "metadata": {"latency_ms": context.latency_ms, "request_id": request_id, "validation_failed": True}
                }
            
            # If the query is out of the system's operational scope, return an immediate refusal.
            # Design decisions (per plan):
            #   - pending_clarification is NOT cleared (validator false-positive is recoverable)
            #   - response is NOT cached (static refusal must not pollute cache keyed by query text)
            #   - intent is returned as "out_of_scope" (not "small_talk") for clean analytics
            #   - language is matched to query language; falls back to English
            if not validation_result.is_in_scope:
                logger.warning(
                    f"[{request_id}] [Validator] Out-of-scope refusal triggered (early gate) for query: '{normalized_question}' "
                    f"(reason={validation_result.scope_reason!r})"
                )
                context.metadata["scope_check"] = {
                    "in_scope": False,
                    "reason": validation_result.scope_reason,
                    "keywords": validation_result.scope_keywords_matched
                }
                from .translator import QueryTranslator
                _oos_lang = "en"
                if context.session_context and getattr(context.session_context, "target_language", None) == "km":
                    _oos_lang = "km"
                elif QueryTranslator.is_khmer(normalized_question):
                    _oos_lang = "km"
                return await self._build_out_of_scope_response(
                    context=context,
                    question=question,
                    normalized_question=normalized_question,
                    session_id=session_id,
                    request_id=request_id,
                    language=_oos_lang,
                    scope_reason=validation_result.scope_reason,
                )

            
            context.metadata["validation_passed"] = True
            context.metadata["scope_keywords_detected"] = validation_result.scope_keywords_matched
            
            # Step 6: Session context already loaded early.
            pass

            # Step 8: Intent Classification & Safety Gates
            _intent_confidence: float = 1.0
            raw_detected_intent = None

            if context.skip_intent_detection:
                # Reuse the previously resolved or manually set intent
                raw_detected_intent = context.intent
            else:
                # Classify intent and confidence scores
                if validation_result.reason and validation_result.reason.startswith("llm_validated:"):
                    val_category = validation_result.reason.split(":", 1)[1]
                    val_confidence = getattr(validation_result, "llm_confidence", 0.8)
                    try:
                        context.intent = WorkflowIntent(val_category)
                    except ValueError:
                        context.intent = WorkflowIntent.UNCLASSIFIED
                    _intent_confidence = val_confidence
                    raw_detected_intent = context.intent
                    logger.info(f"[{request_id}] [Intent+Conf] Reused LLM validation intent classification: {context.intent.value} conf={_intent_confidence:.2f}")
                else:
                    cached_intent = None
                    cached_confidence = 0.8
                    if self.first_layer_service:
                        cache = self.first_layer_service.get_request_unified_result()
                        if cache:
                            norm_q = self.first_layer_service._normalize_key(normalized_question)
                            if self.first_layer_service._normalize_key(cache.get("query", "")) == norm_q:
                                cached_intent = cache.get("intent")
                                cached_confidence = cache.get("confidence", 0.8)
                                logger.info(f"[{request_id}] [Intent+Conf] Reused unified cache intent: {cached_intent} conf={cached_confidence:.2f}")

                    if cached_intent:
                        try:
                            context.intent = WorkflowIntent(cached_intent)
                        except ValueError:
                            context.intent = WorkflowIntent.UNCLASSIFIED
                        _intent_confidence = cached_confidence
                    else:
                        context.intent, _intent_confidence = self.workflow_executor.detect_intent_with_confidence(normalized_question)
                    raw_detected_intent = context.intent
                # Propagate the resolved LLM confidence into context.metadata so that
                # _apply_intent_safety_gate and downstream logging can read it correctly.
                # Without this write, context.metadata.get("llm_confidence") silently
                # returns the default 1.0, rendering any confidence-based guard ineffective.
                context.metadata["llm_confidence"] = _intent_confidence

                # ===== MULTILINGUAL LANGUAGE RESOLUTION & NORMALIZATION =====
                SUPPORTED_SUGGESTION_LANGUAGES = {"en", "km"}
                resolved_lang = "en"
                
                # Fetch structured NLU result from Gemini unified first-layer
                nlu_cache = self.first_layer_service.get_request_unified_result() if self.first_layer_service else None
                if nlu_cache:
                    context.metadata["nlu_unified_result"] = nlu_cache
                req_lang = nlu_cache.get("requested_language") if nlu_cache else None
                is_explicit_lang = nlu_cache.get("is_language_explicitly_requested", False) if nlu_cache else False

                has_nlu_entity = nlu_cache is not None and "entity_confidence" in nlu_cache
                if has_nlu_entity:
                    context.metadata["nlu_entity"] = nlu_cache.get("entity")
                    context.metadata["nlu_entity_confidence"] = nlu_cache.get("entity_confidence")
                    context.metadata["has_nlu_entity"] = True
                else:
                    context.metadata["nlu_entity"] = None
                    context.metadata["nlu_entity_confidence"] = None
                    context.metadata["has_nlu_entity"] = False

                has_khmer_directive = bool(re.search(
                    r"\b(in\s+khmer|translate\s+in\s+khmer|translate\s+into\s+khmer|translate\s+to\s+khmer|khmer\s+output|khmer\s+language|as\s+khmer|to\s+khmer|into\s+khmer|ជាភាសាខ្មែរ|បកប្រែជាភាសាខ្មែរ|ជាខ្មែរ)\b",
                    question.lower()
                ))

                if (is_explicit_lang and req_lang in SUPPORTED_SUGGESTION_LANGUAGES) or has_khmer_directive:
                    resolved_lang = req_lang if (is_explicit_lang and req_lang in SUPPORTED_SUGGESTION_LANGUAGES) else "km"
                    if context.session_context:
                        context.session_context.target_language = resolved_lang
                        context.session_context.is_language_pinned = True
                elif context.session_context and getattr(context.session_context, "is_language_pinned", False):
                    resolved_lang = getattr(context.session_context, "target_language", "en")
                else:
                    from .translator import QueryTranslator
                    if QueryTranslator.is_khmer(question):
                        resolved_lang = "km"
                    elif context.session_context and getattr(context.session_context, "target_language", None) in SUPPORTED_SUGGESTION_LANGUAGES:
                        resolved_lang = context.session_context.target_language
                    else:
                        resolved_lang = "en"

                context.metadata["language"] = resolved_lang
                setattr(context, "language", resolved_lang)
                if context.session_context:
                    context.session_context.target_language = resolved_lang
                    context.session_context.language = resolved_lang

                # Run security check safety gate to prevent malformed or risky intent transitions
                context.intent = self._apply_intent_safety_gate(context, original_query)

                # ── Out-of-scope post-intent gate ────────────────────────────────────────────
                # INTERIM FIX (Phase 1): The first-layer LLM collapses two distinct categories
                # under the single 'small_talk' label: genuine greetings/farewells AND general
                # off-topic knowledge queries. The validator treats both as is_in_scope=True,
                # so the early gate above never fires for off-topic general questions.
                # Here we intercept after intent resolution: if intent is SMALL_TALK but the
                # query doesn't match any genuine conversational pattern (greeting, farewell,
                # identity, casual social — in English or Khmer), we refuse it as out_of_scope.
                #
                # SUPERSEDED BY (Phase 2): Update gemini_unified_first_layer prompt to emit
                # distinct 'greeting' vs 'general_off_topic' labels, removing this regex list.
                # ────────────────────────────────────────────────────────────────────────────
                if context.intent == WorkflowIntent.SMALL_TALK:
                    if not self._is_genuine_conversational_small_talk(normalized_question):
                        logger.warning(
                            f"[{request_id}] [Validator] Out-of-scope refusal triggered (post-intent gate) "
                            f"for query: '{normalized_question}'"
                        )
                        return await self._build_out_of_scope_response(
                            context=context,
                            question=question,
                            normalized_question=normalized_question,
                            session_id=session_id,
                            request_id=request_id,
                            language=resolved_lang,
                            scope_reason="llm_classified_as_small_talk_not_conversational",
                        )

            # Step 10: Dynamic Clarification (Ask-Back) Triggering
            # Trigger ask-back if the intent detection confidence is below 0.75 (meaning the query is ambiguous),
            # or if it's a turn-2+ query that is not self-sufficient.
            _already_resolved = bool(context.metadata.get("clarification_resolved"))
            _turn_number = len(getattr(context.session_context, 'turns', [])) + 1 if context.session_context else 1
            
            should_ask_back = False
            trigger_reason = ""
            
            if not _already_resolved:
                # Retrieve NLU metadata cached during First Layer validation
                nlu_cache = context.metadata.get("nlu_unified_result") or {}
                is_ambig = nlu_cache.get("is_ambiguous") if isinstance(nlu_cache, dict) else None
                nlu_conf = nlu_cache.get("confidence") if isinstance(nlu_cache, dict) else None
                if nlu_conf is None:
                    nlu_conf = _intent_confidence if _intent_confidence is not None else 0.0

                regex_vague = self._is_vague_trade_query(normalized_question)

                if context.intent == WorkflowIntent.TRADE_QUERY:
                    # Implement 7-row decision matrix
                    if nlu_conf >= 0.85:
                        if is_ambig is True:
                            should_ask_back = True
                            trigger_reason = "high_conf_nlu_ambiguous"
                        else:
                            should_ask_back = False
                    elif 0.60 <= nlu_conf < 0.85:
                        if regex_vague:
                            should_ask_back = True
                            trigger_reason = "med_conf_regex_vague"
                        else:
                            should_ask_back = False
                    else:  # nlu_conf < 0.60 or nlu_conf is None (0.0)
                        should_ask_back = True
                        trigger_reason = "low_conf_ambiguous"
                elif _intent_confidence < 0.60:
                    should_ask_back = True
                    trigger_reason = "low_confidence_ambiguous"
                elif (
                    context.session_context
                    and _turn_number >= 2
                    and not self.use_input_rewriter
                    and not self._is_self_sufficient_query(
                        normalized_question, context.intent, _intent_confidence
                    )
                ):
                    should_ask_back = True
                    trigger_reason = "turn2_not_self_sufficient"

            if should_ask_back:
                try:
                    from ..ai import get_llm_first_layer_service as get_ask_back_service
                    ask_back_svc = get_ask_back_service()
                    candidate_scores = self.workflow_executor._estimate_candidate_scores(normalized_question)
                    ask_back_result = await ask_back_svc.get_clarification_async(
                        query=normalized_question,
                        intent_label=context.intent.value,
                        confidence=_intent_confidence,
                        session=context.session_context,
                        candidate_scores=candidate_scores,
                        turn_number=_turn_number,
                    )
                    if ask_back_result.should_ask_back or _intent_confidence < 0.60:
                        # Set session state to await clarification from user
                        if context.session_context:
                            context.session_context.set_pending_clarification(
                                candidate_intents=ask_back_result.candidate_intents,
                                rewritten_query=normalized_question,
                            )
                        context.finalize()
                        return self._build_ask_back_response(
                            context,
                            question=normalized_question,
                            clarification_question=ask_back_result.question,
                            candidate_intents=ask_back_result.candidate_intents,
                            trigger_reason=ask_back_result.trigger_reason or trigger_reason,
                        )
                except Exception as e:
                    logger.warning(f"[{request_id}] Ask-back check failed: {e}")

            # Step 9: Core Intent Filtering (Directing non-core/refusal intents to small talk fallback)
            if context.intent not in {
                WorkflowIntent.CALCULATION,
                WorkflowIntent.TRADE_QUERY,
                WorkflowIntent.HS_CODE_LOOKUP,
                WorkflowIntent.GENERAL,
                WorkflowIntent.SMALL_TALK
            }:
                logger.info(f"[{request_id}] Query intent '{context.intent}' does not match any core intention. Handling as small talk.")
                
                # Treat non-core queries as dynamic conversation fallback
                small_talk_response = await detect_small_talk(normalized_question, self.llm_service, force_llm_fallback=True)
                
                context.intent = WorkflowIntent.SMALL_TALK
                context.status = WorkflowStatus.COMPLETED
                context.finalize()
                
                # Update session history
                if self.use_input_rewriter and session_id:
                    try:
                        self.rewriter_service.update_session_context(session_id, last_intent="small_talk")
                        session_context = self.rewriter_service.get_or_create_session(session_id)
                        session_context.add_turn(user_input=question, bot_response=small_talk_response)
                    except Exception as e:
                        logger.warning(f"[{request_id}] Failed to update session for small talk: {e}")
                
                return {
                    "intent": "small_talk",
                    "status": "completed",
                    "answer": small_talk_response,
                    "sources": [],
                    "metadata": {
                        "latency_ms": context.latency_ms,
                        "session_id": session_id,
                        "request_id": request_id
                    }
                }

            # Step 11: Context-Aware Query Rewriting
            # Use conversation history to resolve pronouns or implied context in the query.
            # Skipping rewriting for TRADE_QUERY, HS_CODE_LOOKUP, and CALCULATION so their
            # downstream services receive the raw query for structured parsing / keyword matching.
            # Only GENERAL (the catch-all NLU intent) goes through the LLM rewrite step.
            context.rewritten_input = original_query
            rewrite_status = "skipped"
            rewrite_skip_reason = self._get_rewrite_skip_reason(intent=context.intent, rewriter_enabled=self.use_input_rewriter)
            context.rewrite_metadata = context.rewrite_metadata or {"rewrite_reason": "not_applied", "reason": "rewrite_disabled_or_skipped"}

            # Determine if the query is an ambiguous follow-up fragment
            is_ambiguous = False
            if context.session_context and len(getattr(context.session_context, 'turns', [])) > 0:
                q_lower = original_query.lower().strip()
                relative_words = [
                    r"\bit\b", r"\bthat\b", r"\bthis\b", r"\bthose\b", r"\bthey\b", r"\bthem\b",
                    r"\bits\b", r"\bthere\b", r"\bhere\b", r"\bprevious\b", r"\babove\b", r"\bsame\b"
                ]
                has_rel = any(re.search(pat, q_lower) for pat in relative_words)
                has_prefix = any(q_lower.startswith(prefix) for prefix in RELATIVE_PREFIXES)
                is_short = len(q_lower.split()) <= 3
                is_ambiguous = has_rel or has_prefix or is_short

            if (
                self.use_input_rewriter
                and raw_detected_intent != WorkflowIntent.SMALL_TALK
            ):
                intent_hint = context.intent.value if context.intent else None
                try:
                    rewritten_question, rewrite_metadata = await self.rewriter_service.rewrite_input(
                        original_query,
                        context=context.session_context,
                        intent_hint=intent_hint,
                    )
                    context.rewritten_input = rewritten_question
                    context.rewrite_metadata = rewrite_metadata
                    rewrite_status = "applied"
                    rewrite_skip_reason = None
                    
                    logger.info(
                        f"[{request_id}] [REWRITE] Input Rewriter: original='{original_query}' "
                        f"-> rewritten='{rewritten_question}' | metadata={rewrite_metadata}"
                    )

                    # If rewriter flags that the original query is better, fallback to original query
                    if isinstance(rewrite_metadata, dict) and rewrite_metadata.get("rewritten") is False:
                        context.rewritten_input = original_query
                        context.rewrite_metadata = {**(rewrite_metadata or {}), "rewrite_reason": "original_better", "validation_status": "skipped_original_better"}
                        rewrite_status = "skipped"
                        rewrite_skip_reason = "original_better"

                    # Validate that rewriting hasn't corrupted or injected hallucinations/bad info into the query.
                    # For GENERAL intent, use a relaxed check — short follow-ups legitimately expand a lot.
                    if not self._is_rewrite_valid(original_query, rewritten_question, intent=context.intent):
                        context.rewritten_input = original_query
                        context.rewrite_metadata = {**(rewrite_metadata or {}), "rewrite_reason": "validation_rejected", "validation_status": "rejected"}
                        rewrite_status = "skipped"
                        rewrite_skip_reason = "rewrite_validation_failed"
                        logger.info(f"[{request_id}] [WARN] Input Rewriter validation rejected. Reverting to original query.")
                    else:
                        context.rewrite_metadata = {**rewrite_metadata, "validation_status": "accepted"}
                except Exception as e:
                    logger.warning(f"[{request_id}] Input rewriting failed: {e}")
                    context.rewritten_input = original_query
                    context.rewrite_metadata = {"error": str(e), "rewrite_reason": "rewrite_failed"}
                    rewrite_status = "skipped"
                    rewrite_skip_reason = "rewrite_error"
            else:
                context.rewrite_metadata = {
                    "rewrite_reason": "not_applied",
                    "reason": "input_rewriter_disabled_or_small_talk",
                    "intent": context.intent.value if context.intent else None,
                }
                logger.info(
                    f"[{request_id}] ⚪ Input Rewriter: skipped (reason: {context.rewrite_metadata.get('reason')})"
                )

            # Step 12: Microservice Selection & Routing
            # Choose whether to route using original query or rewritten query based on rewriting outcomes
            service_query, query_strategy = self._select_service_query(
                original_query=original_query,
                rewritten_query=context.rewritten_input,
                rewrite_applied=(rewrite_status == "applied"),
            )
            context.metadata["intent_query"] = original_query
            context.metadata["service_query"] = service_query
            context.metadata["query_strategy"] = query_strategy

            # Run the postponed safety gate on the final service query (either rewritten or original)
            if context.metadata.get("_safety_gate_postponed"):
                context.metadata["_safety_gate_postponed"] = False
                context.intent = self._apply_intent_safety_gate(context, service_query, postpone_allowed=False)

            target_service = self._resolve_target_service(context.intent)

            # Perform the async microservice routing
            await self._route_query(context)
            
            # Step 13: Update session tracking with processed query info
            if self.use_input_rewriter and session_id and context.session_context:
                try:
                    tracking_query = (
                        context.rewritten_input 
                        if (context.rewrite_metadata or {}).get("validation_status") == "accepted" 
                        else (context.cleaned_input or context.original_input or question)
                    )
                    # ---- Two-turn state: populate last_intent / last_entity / last_*_query ----
                    update_kwargs = self._build_session_update_payload(
                        raw_query=question,
                        normalized_query=tracking_query,
                        intent_value=context.intent.value if context.intent else None,
                        detected_currency=context.detected_currency,
                        session_context=context.session_context,
                        nlu_entity=context.metadata.get("nlu_entity"),
                        has_nlu_entity=context.metadata.get("has_nlu_entity", False),
                        nlu_entity_confidence=context.metadata.get("nlu_entity_confidence"),
                    )
                    self.rewriter_service.update_session_context(session_id, **update_kwargs)



                    if not stream:
                        # Synchronous mode: save turn with placeholder answer summary now.
                        answer_summary = "Query processed"
                        if context.retrieval_result and context.retrieval_result.get("documents"):
                            docs = context.retrieval_result.get("documents", [])
                            if docs:
                                answer_summary = f"Found {len(docs)} relevant documents"
                        context.session_context.add_turn(user_input=context.original_input, bot_response=answer_summary[:200])
                    # In stream mode, add_turn is called by the endpoint after the full streamed
                    # response is assembled, so we skip it here.

                except Exception as e:
                    logger.warning(f"[{request_id}] Failed to update session: {e}")

            # Finalize context and build orchestrator response package
            context.finalize()

            # Log intent routing and context data to DB in a context-isolated way
            try:
                from app.infrastructure import get_db_context, message_id_var
                from app.services.db_service import ChatbotDBService
                
                msg_id = message_id_var.get()
                with get_db_context() as db:
                    await ChatbotDBService.save_intent_route(
                        db=db,
                        session_id=session_id,
                        message_id=msg_id,
                        intent=context.intent.value if context.intent else "unclassified",
                        service=self._resolve_target_service(context.intent),
                        confidence=_intent_confidence
                    )
                    if context.session_context:
                        await ChatbotDBService.save_session_context(
                            db=db,
                            session_id=session_id,
                            context_data=context.session_context.to_dict()
                        )
            except Exception as db_err:
                logger.error(f"[{request_id}] Failed to log intent route / session context to DB: {db_err}")

            if stream:
                # Return raw context so the streaming endpoint can drive generation.
                # The endpoint reads: answer, intent, sources, metadata, session_context.
                raw = await self._build_response(context)
                raw["_stream"] = True
                raw["_session_context"] = context.session_context
                raw["_original_input"] = context.original_input
                return raw

            return await self._build_response(context)

        except Exception as e:
            # Handle unexpected orchestration pipeline errors cleanly
            logger.error(f"[{request_id}] Error processing query: {e}")
            context.add_error(str(e))
            context.status = WorkflowStatus.FAILED
            context.finalize()
            return await self._build_error_response(context)


    # Decide which service should be sent to downstream services
    def _select_service_query(self, original_query: str, rewritten_query: Optional[str], rewrite_applied: bool) -> tuple[str, str]:
        if rewrite_applied and rewritten_query and rewritten_query.strip():
            return rewritten_query, "rewritten_after_llm"
        return original_query, "original_for_no_rewrite_or_skipped"

    # Check if the user's request needs a search/retrieval system.
    def _is_retrieval_intent(self, intent: WorkflowIntent) -> bool:
        return intent in {WorkflowIntent.HS_CODE_LOOKUP, WorkflowIntent.GENERAL, WorkflowIntent.UNCLASSIFIED}


    # Decide which backend service handles the request.
    def _resolve_target_service(self, intent: WorkflowIntent) -> str:
        if intent == WorkflowIntent.CALCULATION: return "calculator"
        if intent == WorkflowIntent.TRADE_QUERY: return "trade_data"
        if intent == WorkflowIntent.GENERAL: return "general"
        if intent == WorkflowIntent.SMALL_TALK: return "small_talk"
        return "retrieval"

    def _merge_pending_with_clarification(
        self,
        pending_query: str,
        clarification_response: str,
        resolved_intent: str,
        session_last_entity: Optional[str] = None,
        session_context: Optional[Any] = None,
        was_clarification_pending: bool = False,
    ) -> str:
        return ClarificationManager.merge_pending_with_clarification(
            self,
            pending_query,
            clarification_response,
            resolved_intent,
            session_last_entity,
            session_context,
            was_clarification_pending,
        )

    def _validate_merged_query(self, merged_query: str, resolved_intent: str) -> bool:
        return ClarificationManager.validate_merged_query(self, merged_query, resolved_intent)


    def _looks_like_commercial_description(self, text: str) -> bool:
        return Heuristics.looks_like_commercial_description(text)

    def _is_entity_clearing_correction(self, query: str) -> bool:
        """
        Check if query is a grammatical correction fragment targeting the entity slot.
        Temporary stopgap before LLM returns is_correction_fragment directly.
        """
        cleaned = query.strip().lower()
        negation_patterns = [
            r"^(?:actually\s+)?none$",
            r"^(?:actually\s+)?no\s+(?:product|commodity|entity|item|goods)$",
            r"^clear\s+(?:product|commodity|entity|item|goods)$",
            r"^remove\s+(?:product|commodity|entity|item|goods)$",
            r"^not\s+a\s+(?:product|commodity|entity|item|goods)$",
            r"^គ្មានទេ$",
            r"^មិនមែនទំនិញទេ$",
        ]
        return any(re.match(pat, cleaned) for pat in negation_patterns)

    def _build_session_update_payload(
        self,
        raw_query: str,
        normalized_query: str,
        intent_value: Optional[str],
        detected_currency: Optional[str] = None,
        session_context: Optional[Any] = None,
        nlu_entity: Optional[str] = None,
        has_nlu_entity: bool = False,
        nlu_entity_confidence: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Helper to build standardized session state kwargs across turns."""
        from .hs_classifier import detect_simple_product_category
        category = detect_simple_product_category(normalized_query)
        q_lower = normalized_query.lower()
        mode = "import" if "import" in q_lower else "export" if "export" in q_lower else None

        prev_entity = getattr(session_context, "last_entity", None) if session_context else None
        last_entity_val = prev_entity
        entity_state_log = "fallback_preserved"

        # State 1: High-confidence NLU entity found
        if has_nlu_entity and nlu_entity and nlu_entity_confidence == "high":
            last_entity_val = nlu_entity
            entity_state_log = "found"

        # State 2: Explicit confirmation of no entity
        elif has_nlu_entity and (not nlu_entity) and nlu_entity_confidence == "explicit_none":
            if self._is_entity_clearing_correction(raw_query):
                last_entity_val = None
                entity_state_log = "explicit_none_cleared"
            else:
                last_entity_val = prev_entity
                entity_state_log = "explicit_none_preserved"

        # State 3: Regex fallback / Low confidence / Gemini down
        else:
            # We preserve long-term last_entity, but we can still compute a current-turn entity
            # for immediate use (RAG search, suggestions, etc.) if needed via regex.
            last_entity_val = prev_entity
            entity_state_log = "fallback_preserved"

        logger.debug(
            f"[ENTITY_STATE] state: {entity_state_log} | "
            f"raw_query: '{raw_query}' | "
            f"nlu_entity: '{nlu_entity}' (conf: {nlu_entity_confidence}) | "
            f"has_nlu_entity: {has_nlu_entity} | "
            f"prev_entity: '{prev_entity}' -> last_entity: '{last_entity_val}'"
        )

        update_kwargs = {
            "last_intent": intent_value,
            "last_raw_query": raw_query,
            "last_normalized_query": normalized_query,
            "last_entity": last_entity_val,
        }
        if detected_currency:
            update_kwargs["currency"] = detected_currency
        if category and category != "other":
            update_kwargs["product_category"] = category
        if mode:
            update_kwargs["import_export_mode"] = mode
        return update_kwargs

    def update_session_for_query(
        self,
        session_id: str,
        query: str,
        intent_value: str,
        normalized_query: Optional[str] = None,
        detected_currency: Optional[str] = None,
        answer_summary: str = "Query processed",
    ):
        """Updates session state for cache hit queries to preserve context on subsequent turns."""
        if not self.use_input_rewriter or not session_id:
            return
        try:
            session_context = self.rewriter_service.get_or_create_session(session_id)
            cleaned_query = self.workflow_executor.cleanup_query(query) or query
            update_kwargs = self._build_session_update_payload(
                raw_query=query,
                normalized_query=cleaned_query,
                intent_value=intent_value,
                detected_currency=detected_currency,
                session_context=session_context
            )
            self.rewriter_service.update_session_context(session_id, **update_kwargs)
            session_context.add_turn(user_input=query, bot_response=answer_summary[:200])
        except Exception as e:
            logger.warning(f"Failed to update session for query {query}: {e}")


    async def _build_out_of_scope_response(
        self,
        context: WorkflowContext,
        question: str,
        normalized_question: str,
        session_id: str,
        request_id: str,
        language: str,
        scope_reason: str,
    ) -> Dict[str, Any]:
        """
        Single shared helper that constructs the out_of_scope refusal response.
        Called by BOTH refusal gates (early validator gate and post-intent gate)
        to guarantee identical behaviour:
          - Calls generate_out_of_scope_refusal() — LLM-driven, with static fallback
          - Attaches localized generic_fallback suggestion chips
          - Returns intent: 'out_of_scope' (never 'small_talk')
          - Does NOT clear pending_clarification/session state (false-positive is recoverable)
          - Does NOT cache the response
        """
        _refusal_text = await generate_out_of_scope_refusal(
            query=question,
            llm_service=self.llm_service,
            language=language,
        )
        _oos_suggestions: list = []
        try:
            _oos_suggestions = self.suggestion_service.get_suggestions(
                current_intent="small_talk",
                rewritten_query=normalized_question,
                session_context=context.session_context,
                language=language,
                nlu_entity=context.metadata.get("nlu_entity"),
                has_nlu_entity=context.metadata.get("has_nlu_entity", False),
            )
        except Exception:
            pass
        context.finalize()
        return {
            "request_id": request_id,
            "question": question,
            "intent": "out_of_scope",
            "status": "completed",
            "latency_ms": context.latency_ms,
            "answer": _refusal_text,
            "citations": [],
            "suggestion": _oos_suggestions,
            "metadata": {
                "request_id": request_id,
                "session_id": session_id,
                "out_of_scope": True,
                "scope_reason": scope_reason,
            }
        }

    def _is_genuine_conversational_small_talk(self, query: str) -> bool:
        return Heuristics.is_genuine_conversational_small_talk(query)

    def _apply_intent_safety_gate(self, context: WorkflowContext, original_query: str, postpone_allowed: bool = True) -> WorkflowIntent:
        """
        Safety mechanism that can override or adjust the detected intent based on 
        additional analysis. Prevents false classifications and corrects intent misdetections.
        """
        # Get the intent that was already detected by earlier logic
        detected_intent = context.intent

        if detected_intent == WorkflowIntent.HS_CODE_LOOKUP:
            # Even when LLM classifies as HS_CODE_LOOKUP, run a sanity check:
            # if the query looks like a greeting/typo (not a product description),
            # downgrade it to SMALL_TALK to avoid routing gibberish into the retrieval pipeline.
            candidate_query = original_query or context.cleaned_input
            if not self._looks_like_short_product_lookup(candidate_query) and not self._looks_like_commercial_description(candidate_query):
                # Check if it contains any HS-specific keywords that make it genuinely an HS query.
                # IMPORTANT: use `context.question` (the raw, unmodified user input from WorkflowContext),
                # NOT `context.cleaned_input` or `original_query` — cleanup_query() intentionally strips
                # "hs code" suffix patterns via FILLER_PATTERNS, so those variables lose the keyword signal.
                # e.g. "can you help me with hs code" → cleaned: "can you help me with" (keyword gone).
                raw_lower = (original_query if not postpone_allowed else (context.question or original_query or "")).strip().lower()
                has_hs_keyword = any(
                    re.search(rf"\b{re.escape(kw)}\b", raw_lower)
                    for kw in ["hs", "code", "tariff", "classify", "classification", "hts", "import", "export", "duty", "tax", "cbu", "ckd", "skd"]
                )
                if not has_hs_keyword:
                    is_follow_up = self.use_input_rewriter and context.session_context and len(getattr(context.session_context, 'turns', [])) > 0
                    if postpone_allowed and is_follow_up:
                        logger.info(
                            f"[{context.request_id}] [SAFETY-GATE] Postponing HS_CODE_LOOKUP downgrade to SMALL_TALK for follow-up query: '{original_query}'"
                        )
                        if not context.metadata:
                            context.metadata = {}
                        context.metadata["_safety_gate_postponed"] = True
                        return detected_intent

                    # Bare short word that passed NLU as HS_CODE_LOOKUP but has no
                    # HS keywords and isn't a product description — treat as small talk.
                    logger.info(
                        f"[{context.request_id}] [SAFETY-GATE] HS_CODE_LOOKUP flagged for"
                        f" '{raw_lower[:40]}' but no HS keyword or product description found."
                        " Downgrading to SMALL_TALK."
                    )
                    return WorkflowIntent.SMALL_TALK
        if detected_intent == WorkflowIntent.CALCULATION:
            # Safety check: if the query is a generic/conceptual/educational query about
            # how calculation works rather than requesting an actual calculation for a product,
            # and it lacks specific parameters (cif, product), route it to GENERAL.
            raw_lower = (context.original_input or original_query or "").strip().lower()
            
            # Primary path: utilize the LLM-classified query_nature (multilingual ready)
            nlu_result = context.metadata.get("nlu_unified_result") or {}
            query_nature = nlu_result.get("query_nature")
            
            should_downgrade = False
            downgrade_reason = ""
            
            if query_nature == "procedural":
                should_downgrade = True
                downgrade_reason = "LLM query_nature == 'procedural'"
            else:
                # Fallback path: regex matching if query_nature is unavailable
                procedural_patterns = [
                    r"\bhow\s+(?:is|are)\s+.*calculated\b",
                    r"\bhow\s+to\s+calculate\s+(?:duty|tax|tariff|customs)\b",
                    r"\bformula\s+(?:for|of)\b",
                    r"\bexplain\s+how\s+.*is\s+calculated\b",
                    r"\bwhat\s+(?:is|are)\s+the\s+rules?\s+for\s+calculat\b",
                    r"\bhow\s+do\s+you\s+calculate\b",
                    r"\bprocedure\s+for\s+calculat\b",
                    r"\bhow\s+.*\b(?:duty|tax|tariff|customs)\s+works?\b",
                    r"\bexplain\s+.*\b(?:duty|tax|tariff|customs|calculation)\b"
                ]
                # Avoid blunt numeric checks (ignoring bare HS codes without CIF prices)
                has_priceable_amount = bool(re.search(
                    r'[$€£¥₩]\s*\d+|\d+\s*[$€£¥₩]|\b(?:cif|fob|usd|khr)\b', 
                    raw_lower
                ))
                if any(re.search(pat, raw_lower) for pat in procedural_patterns) and not has_priceable_amount:
                    should_downgrade = True
                    downgrade_reason = "regex fallback matching procedural pattern without priceable amount"
            
            if should_downgrade:
                logger.info(
                    f"[{context.request_id}] [SAFETY-GATE] Downgrading CALCULATION to GENERAL. "
                    f"Reason: {downgrade_reason} | query: '{raw_lower[:50]}'"
                )
                # Explicitly clear all spec and intent clarification states on the session
                if context.session_context:
                    context.session_context.product_clarification_needed = False
                    context.session_context.clarification_entity = None
                    context.session_context.clarification_last_query = None
                    context.session_context.product_ask_back_count = 0
                    context.session_context.clarification_expected_terms = []
                    context.session_context.pending_clarification = False
                    context.session_context.clarification_intents = []
                    context.session_context.ask_back_count = 0
                    context.session_context.pending_rewritten_query = None
                    context.session_context._trigger_change()
                return WorkflowIntent.GENERAL
            return detected_intent

        # For GENERAL / UNCLASSIFIED intents the LLM is trusted unconditionally.
        # Genuinely ambiguous queries (low confidence) are already handled by the
        # Step 10 ask-back loop at L739 (_intent_confidence < 0.60 → ask-back fires).
        # Heuristic overrides that could flip a correct GENERAL classification into
        # HS_CODE_LOOKUP or TRADE_QUERY have been removed: they caused the class of
        # bug where "but which one more costly??" was forced into HS_CODE_LOOKUP
        # even though Gemini returned GENERAL at 0.98 confidence.
        if detected_intent in {WorkflowIntent.GENERAL, WorkflowIntent.UNCLASSIFIED}:
            return detected_intent

        # No reclassification needed; return the original detected intent
        return detected_intent

    def _looks_like_trade_data_query(self, query: str) -> bool:
        return Heuristics.looks_like_trade_data_query(query)

    def _looks_like_short_product_lookup(self, query: str) -> bool:
        return Heuristics.looks_like_short_product_lookup(query)

    # ------------------------------------------------------------------ #
    # Product-spec clarification state machine – helpers                  #
    # ------------------------------------------------------------------ #

    async def _try_merge_product_spec(
        self,
        context,
        request_id: str,
        question: str,
        normalized_question: str,
        session_id: Optional[str],
    ):
        return await ClarificationManager.try_merge_product_spec(
            self,
            context,
            request_id,
            question,
            normalized_question,
            session_id,
        )

    def _clear_product_clarification(self, session) -> None:
        return ClarificationManager.clear_product_clarification(session)

    @staticmethod
    def _build_spec_expected_terms(
        clarifying_questions: Optional[list],
        category: str,
    ) -> list:
        return ClarificationManager.build_spec_expected_terms(clarifying_questions, category)

    def _query_has_explicit_intent(self, query: str) -> bool:
        """
        HIGH-CONFIDENCE intent detector: checks if query EXPLICITLY states intent via keywords.
        Used to establish baseline intent confidence before falling back to heuristics. 
        """
        q = (query or "").lower()
        hs_signals = ["hs", "hs code", "hs-code", "hscode", "ahtn", "tariff code", "harmonized code", "classify", "classification"]
        if any(sig in q for sig in hs_signals): 
            return True
        calc_signals = ["calculate", "compute", "how much duty", "import duty", "import tax", "customs duty", "duty rate", "cif value", "fob value", "net mass", "volume"]
        if any(sig in q for sig in calc_signals): 
            return True
        trade_signals = ["trade data", "trade statistics", "trade volume", "trade flow", "bilateral trade", "export data", "import data"]
        if any(sig in q for sig in trade_signals): 
            return True
        policy_signals = ["procedure", "process", "steps", "how to import", "how to export", "what documents", "regulation", "compliance"]
        if any(sig in q for sig in policy_signals): 
            return True
        definition_signals = ["what is", "define ", "definition of", "explain ", "meaning of"]
        if any(sig in q for sig in definition_signals): 
            return True
        return False

    def _get_rewrite_skip_reason(self, intent: WorkflowIntent, rewriter_enabled: bool) -> str:
        """
        Determines the reason for skipping query rewriting based on intent and rewriter status.
        """
        if not rewriter_enabled:
            return "input_rewriter_disabled"
        if intent == WorkflowIntent.SMALL_TALK:
            return "small_talk rule"
        return "rewrite_allowed"
    
    def _is_self_sufficient_query(
        self, query: str, intent: WorkflowIntent, confidence: float
    ) -> bool:
        """
        Return True when a turn-2 query states its own intent clearly enough
        that ask-back clarification should be skipped and the query routed
        directly.

        Two independent criteria — either one is enough:
        1. Confidence >= turn2_self_sufficiency_threshold (0.75).
           Intentionally STRICTER than the pipeline-level ambiguity_confidence_
           threshold (0.65) for two reasons:
           (a) Turn-2 fragments are noisier inputs than full turn-1 queries.
           (b) A wrong routing decision here silently produces a complete-
               looking but wrong-context query, which is harder for the user
               to catch than an ordinary low-confidence result.
        2. The query contains explicit intent-signalling keywords (independent
           of model confidence).
        """
        # Conversational followups (e.g., "what about", "how about", "and for")
        # are fragments and are never self-sufficient.
        q_lower = query.lower().strip()
        if any(q_lower.startswith(prefix) for prefix in RELATIVE_PREFIXES):
            return False

        # Intentionally separate and stricter than ambiguity_confidence_threshold.
        TURN2_SELF_SUFFICIENCY_THRESHOLD = 0.60

        if confidence >= TURN2_SELF_SUFFICIENCY_THRESHOLD:
            return True

        # Explicit-keyword check: high-confidence keywords override model score
        # ONLY if confidence is at least 0.60. If confidence is below 0.60, it is
        # ambiguous and we do not guess the intention.
        return False

    def _tokens_match(self, t1: str, t2: str) -> bool:
        """Determines if two tokens match, allowing for typos, plurals, and tenses."""
        if t1 == t2:
            return True
        # Handle plurals/grammatical suffix variations
        if t1.rstrip('s') == t2.rstrip('s'):
            return True
        if len(t1) >= 4 and len(t2) >= 4:
            if t1.startswith(t2) or t2.startswith(t1):
                return True
        # Handle common transposition typos (like bwm -> bmw, htc -> hct)
        if len(t1) >= 3 and len(t2) == len(t1):
            if sorted(t1) == sorted(t2):
                # Allow at most 1 transposition (max 2 character differences)
                diff = sum(1 for c1, c2 in zip(t1, t2) if c1 != c2)
                if diff <= 2:
                    return True
        # Handle single-character difference typos for tokens of length >= 4 (e.g. build vs built)
        if len(t1) >= 4 and len(t2) == len(t1):
            diff = sum(1 for c1, c2 in zip(t1, t2) if c1 != c2)
            if diff <= 1:
                return True
        return False

    def _is_rewrite_valid(self, original_query: str, rewritten_query: str, intent: Optional[WorkflowIntent] = None) -> bool:
        """
        Validates that a rewritten query preserves essential structured tokens (codes, specs, numbers)
        from the original query while trusting the LLM rewriter to decide semantic phrasing.
        """
        original_tokens = self._rewrite_tokens(original_query)
        rewritten_tokens = self._rewrite_tokens(rewritten_query)

        if not rewritten_tokens:
            return False

        # Structured tokens = tokens containing digits, dots, or dashes (e.g. HS codes, years, engine sizes like "500cc", "8703.23")
        # Ensure these critical identifiers from the original query are preserved in the rewrite.
        structured_tokens = {token for token in original_tokens if any(char.isdigit() for char in token) or "." in token or "-" in token}
        if structured_tokens and not structured_tokens.issubset(set(rewritten_tokens)):
            return False

        # Trust the LLM rewriter decision for semantic query reconstruction
        return True
    
    # Tokenizes text into a list of word/number/identifier tokens.(for sematic purpose)
    def _rewrite_tokens(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9][a-z0-9\.-]*", text.lower())

    def _light_normalize_query(self, user_input: str) -> str:
        normalized = user_input.strip().lower()
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    # Determines which query text to send to downstream retrieval/calculation services.
    def _get_service_query(self, context: WorkflowContext) -> str:
        service_query = context.metadata.get("service_query") if context.metadata else None
        return service_query if service_query else (context.cleaned_input or context.question)
    
    async def _route_query(self, context: WorkflowContext):
        intent = context.intent
        if intent == WorkflowIntent.CALCULATION: await self._handle_calculation(context)
        elif intent == WorkflowIntent.TRADE_QUERY: await self._handle_trade_query(context)
        elif intent == WorkflowIntent.HS_CODE_LOOKUP: await self._handle_hs_code_lookup(context)
        elif intent == WorkflowIntent.GENERAL: await self._handle_default(context)
        elif intent == WorkflowIntent.SMALL_TALK: await self._handle_small_talk(context)
        else: await self._handle_default(context)
    
    async def _execute_service_call(self, context: WorkflowContext, service_name: str, client_call_fn, request_payload: Dict[str, Any]):
        import time
        from app.infrastructure import get_db_context
        from app.services.db_service import ChatbotDBService, sync_save_service_call, sync_save_failed_request
        
        start_time = time.time()
        try:
            result = await client_call_fn()
            latency_ms = (time.time() - start_time) * 1000.0
            latency_s = latency_ms / 1000.0

            # Track per-service response time in seconds on the context for API response surfacing
            context.metadata.setdefault("service_latencies_s", {})[service_name] = round(latency_s, 3)

            # Log successful service call
            try:
                with get_db_context() as db:
                    sync_save_service_call(
                        db=db,
                        session_id=context.session_id,
                        service_name=service_name,
                        request_payload=request_payload,
                        response_payload=result,
                        latency_ms=latency_ms,
                        status="success"
                    )
            except Exception as db_err:
                logger.error(f"Failed to log service_call '{service_name}' to DB: {db_err}")

            return result
        except Exception as e:
            latency = (time.time() - start_time) * 1000.0
            
            # Log failed service call & failed request
            try:
                with get_db_context() as db:
                    sync_save_service_call(
                        db=db,
                        session_id=context.session_id,
                        service_name=service_name,
                        request_payload=request_payload,
                        response_payload={"error": str(e)},
                        latency_ms=latency,
                        status="failed"
                    )
                    sync_save_failed_request(
                        db=db,
                        session_id=context.session_id,
                        service_name=service_name,
                        error_message=str(e),
                        error_type=type(e).__name__,
                        request_payload=request_payload
                    )
            except Exception as db_err:
                logger.error(f"Failed to log failed_request '{service_name}' to DB: {db_err}")
            raise

    def _enrich_calculation_query_from_context(self, service_query: str, session_context: Optional[Any]) -> str:
        return CalculationHandler.enrich_calculation_query_from_context(self, service_query, session_context)

    async def _handle_calculation(self, context: WorkflowContext):
        await CalculationHandler.handle(self, context)
    
    def _is_slot_fragment_reply(self, user_text: str, clarification_intents: list) -> bool:
        return Heuristics.is_slot_fragment_reply(user_text, clarification_intents)

    async def _generate_trade_clarification_message(
        self,
        query: str,
        missing_slots: List[str],
        product_name: str
    ) -> str:
        return await TradeQueryHandler.generate_trade_clarification_message(
            self,
            query,
            missing_slots,
            product_name,
        )

    async def _handle_trade_query(self, context: WorkflowContext):
        await TradeQueryHandler.handle(self, context)

    async def _handle_hs_code_lookup(self, context: WorkflowContext):
        await HsCodeLookupHandler.handle(self, context)
    
    def _is_rag_no_info_response(self, answer_text: str, result_dict: dict) -> bool:
        """Determines if the RAG response indicates no information was found in official documents."""
        if not result_dict or not isinstance(result_dict, dict):
            return True
        if result_dict.get("is_generic") is True:
            return True
        if not answer_text:
            return True
        low = answer_text.lower()
        no_info_patterns = [
            "no definition",
            "no information",
            "not contain information",
            "does not contain information",
            "do not contain information",
            "not mentioned in the provided documents",
            "not mentioned in the documents",
            "based on the provided documents",
            "provided documents do not contain",
            "provided documents do not",
            "no specific information",
            "is not mentioned",
            "there is no information",
            "cannot find information",
        ]
        return any(pat in low for pat in no_info_patterns)

    async def _generate_parametric_definition_answer(self, query: str) -> str:
        return await DefinitionHandler.generate_parametric_definition_answer(self, query)

    async def _handle_definition(self, context: WorkflowContext):
        await DefinitionHandler.handle(self, context)
    
    async def _handle_default(self, context: WorkflowContext):
        try:
            if not self.general_client:
                context.add_error("General service not configured")
                context.status = WorkflowStatus.FAILED
                return
            timeout_sec = min(self.timeout_config.get_intent_timeout(context.intent), self.timeout_config.get_service_timeout("general"))
            cache = get_cache_service()
            service_query = self._get_service_query(context)
            cached_result = cache.get_cached_response(service_query, intent="general")
            if cached_result:
                context.set_result("retrieval", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return
                
            async def run_call():
                return await asyncio.wait_for(
                    self.general_client.ask(query=service_query, top_k=5, generate_answer=True, session_id=context.session_id), timeout=timeout_sec
                )

            result = await self._execute_service_call(
                context=context,
                service_name="general",
                client_call_fn=run_call,
                request_payload={"query": service_query, "top_k": 5, "generate_answer": True, "session_id": context.session_id}
            )

            # Fallback check: If RAG returned no document info, use direct LLM parametric knowledge
            if result and isinstance(result, dict):
                ans_text = result.get("final_answer") or result.get("answer") or ""
                if self._is_rag_no_info_response(ans_text, result):
                    logger.info(f"[{context.request_id}] RAG returned no document info for query '{service_query}'. Invoking LLM parametric fallback.")
                    parametric_ans = await self._generate_parametric_definition_answer(service_query)
                    result["answer"] = parametric_ans
                    result["final_answer"] = parametric_ans
                    result["source"] = "llm_parametric_knowledge"

            cache.cache_response(question=service_query, response=result, intent="general", ttl_seconds=24*3600, source="general")
            context.set_result("retrieval", result)
            context.status = WorkflowStatus.COMPLETED
        except Exception as e:
            context.add_error(f"General service error: {str(e)}")
            context.status = WorkflowStatus.FAILED
            
    async def _handle_small_talk(self, context: WorkflowContext):
        await SmallTalkHandler.handle(self, context)

    def _build_ask_back_response(self, context: WorkflowContext, question: str, clarification_question: str, candidate_intents: list, trigger_reason: str = "") -> Dict[str, Any]:
        return {
            "request_id": context.request_id,
            "question": context.question,
            "intent": "clarification_required",
            "status": "clarification_required",
            "latency_ms": context.latency_ms,
            "answer": clarification_question,
            "citations": [],
            "metadata": {"clarification": {"candidate_intents": candidate_intents, "trigger_reason": trigger_reason, "pending_query": question}},
        }

    async def _build_response(self, context: WorkflowContext) -> Dict[str, Any]:
        """Build final response from workflow context."""
        response = {
            "request_id": context.request_id,
            "question": context.question,
            "intent": context.intent.value if context.intent else None,
            "status": context.status.value,
            "latency_ms": context.latency_ms,
            "answer": None,
            "citations": [],
            "metadata": {}
        }
        
        if context.small_talk_result:
            response["answer"] = context.small_talk_result.get("answer")
            if "metadata" in context.small_talk_result and isinstance(context.small_talk_result["metadata"], dict):
                response["metadata"].update(context.small_talk_result["metadata"])
        
        # ===== DIRECT EXTRACT FOR RETRIEVAL/HS_CODE_LOOKUP RESULT =====
        if context.retrieval_result:
            questions = context.retrieval_result.get("clarifying_questions") or []
            if questions:
                for q in questions:
                    if q not in context.clarifications:
                        context.add_clarification(q)
            
            raw_answer = context.retrieval_result.get("final_answer", "No response generated by retrieval service.")
            cleaned_answer = strip_clarification_questions_from_prose(raw_answer, questions)
            response["answer"] = cleaned_answer
            
            # Forward standard citations directly from payload documents without manual text rebuilding
            documents = context.retrieval_result.get("documents", [])
            response["citations"] = [{"doc_id": d.get("id"), "snippet": (d.get("content", "") or d.get("metadata", {}).get("description", "")).strip()[:200], "score": d.get("score", 0), "source": d.get("source", "semantic")} for d in documents]
            response["metadata"] = {
                "semantic_count": context.retrieval_result.get("semantic_count", 0),
                "structured_count": context.retrieval_result.get("structured_count", 0),
                "total_count": context.retrieval_result.get("total_count", 0),
                "answer_source": context.retrieval_result.get("answer_source", "unknown")
            }
            if isinstance(context.retrieval_result.get("metadata"), dict):
                response["metadata"].update(context.retrieval_result["metadata"])
            if context.metadata:
                response["metadata"].update(context.metadata)
        
        if context.calculation_result:
            calc_res = context.calculation_result
            provider_name = str(getattr(self.llm_service, "provider", "") or "").lower() if self.llm_service else ""
            
            # Ollama safety rule: Direct route to DeterministicCalculationFormatter to prevent math hallucinations
            if provider_name == "ollama":
                from ..ai.core.calculation_formatter import DeterministicCalculationFormatter
                response["answer"] = DeterministicCalculationFormatter.format(calc_res, context.question)
            else:
                response["answer"] = (
                    calc_res.get("human_readable") or
                    calc_res.get("answer") or
                    calc_res.get("final_answer") or
                    calc_res.get("formatted_answer") or
                    calc_res.get("message")
                )
                # Run NumericIntegrityValidator on LLM formatted text if valid result
                if response["answer"] and calc_res.get("success") is not False and calc_res.get("total") is not None:
                    from ..ai.core.calculation_formatter import NumericIntegrityValidator, DeterministicCalculationFormatter
                    validator = NumericIntegrityValidator()
                    is_valid, val_errors = validator.validate(response["answer"], calc_res)
                    if not is_valid:
                        logger.warning(f"[{context.request_id}] LLM calculation output failed numeric integrity validation: {val_errors}. Demoting to DeterministicCalculationFormatter.")
                        response["answer"] = DeterministicCalculationFormatter.format(calc_res, context.question)

            if not response["answer"] and calc_res.get("total") is not None and calc_res.get("success") is not False:
                total = calc_res.get("total", 0)
                currency = calc_res.get("currency", "KHR")
                response["answer"] = f"Total Import/Export Taxes and Duties: {total:,.0f} {currency}"
            if isinstance(calc_res.get("metadata"), dict):
                response["metadata"].update(calc_res.get("metadata", {}))
            if calc_res.get("references"):
                response["citations"] = calc_res.get("references", [])
        
        if context.trade_query_result:
            trade_res = context.trade_query_result

            # 1. Message: natural-language answer text (populated in both message and answer)
            message_text = (
                trade_res.get("message") or
                trade_res.get("answer") or
                trade_res.get("final_answer") or
                "No response generated by trade service."
            )

            # If trade status is no_data or 0 records match query criteria, generate a friendly, graceful LLM response in Orchestrator
            is_no_data = (
                trade_res.get("status") == "no_data"
                or trade_res.get("count") == 0
                or (isinstance(trade_res.get("records"), list) and len(trade_res["records"]) == 0 and isinstance(trade_res.get("data"), list) and len(trade_res["data"]) == 0)
                or message_text.startswith("No trade data found for")
                or "no trade data" in message_text.lower()
            )

            if is_no_data:
                try:
                    prompt_template = _prompt_manager.get_system_prompt("gemini_format_no_data")
                    if prompt_template and self.llm_service and self.llm_service.is_available():
                        prompt = prompt_template.format(question=context.question)
                        provider = self.llm_service.router.providers.get("gemini")
                        if provider and provider.is_available():
                            llm_resp = await asyncio.to_thread(
                                provider.client.models.generate_content,
                                model=provider.model_name,
                                contents=prompt,
                            )
                            content = (llm_resp.text or "").strip()
                            if content:
                                message_text = content
                except Exception as e:
                    logger.warning(f"[{context.request_id}] Orchestrator no_data LLM response generation failed: {e}")

                if message_text.startswith("No trade data found for") or "no trade data" in message_text.lower():
                    message_text = "I couldn't find any trade statistics matching your specific query. Try adjusting your search filters, such as selecting a different year, partner country, or commodity."

            response["message"] = message_text
            response["answer"] = message_text

            # 2. Status override if provided in trade response
            if trade_res.get("status"):
                response["status"] = trade_res["status"]

            # 3. Table: include ONLY if non-empty rows exist; drop raw 'records' array
            tbl = trade_res.get("table")
            if isinstance(tbl, dict) and tbl.get("rows") and len(tbl["rows"]) > 0:
                response["table"] = {
                    "columns": tbl.get("columns", []),
                    "rows": tbl["rows"],
                }

            # 4. Visualization: include ONLY if non-empty labels and datasets exist
            viz = trade_res.get("visualization")
            if isinstance(viz, dict) and viz.get("type") and viz.get("labels") and len(viz.get("labels", [])) > 0:
                response["visualization"] = viz

            # 5. Suggestion: include ONLY if non-empty list exists
            sug = trade_res.get("suggestion") or trade_res.get("suggestions")
            if isinstance(sug, list) and len(sug) > 0:
                response["suggestion"] = sug

            # 6. Summary: include data_quality if truncation_note, has_more, is_partial_period, or period_was_defaulted is present
            summary_raw = trade_res.get("summary")
            query_params = trade_res.get("query_params") or {}
            extra_params = query_params.get("extra") if isinstance(query_params, dict) else {}

            if isinstance(summary_raw, dict):
                dq = summary_raw.get("data_quality") if isinstance(summary_raw.get("data_quality"), dict) else {}
                
                period_defaulted = bool(
                    (isinstance(extra_params, dict) and extra_params.get("period_was_defaulted")) or
                    dq.get("period_was_defaulted")
                )
                has_truncation = bool(dq.get("truncation_note") or dq.get("has_more"))
                has_partial = bool(dq.get("is_partial_period") or dq.get("partial_year_note"))
                has_mismatch = bool(dq.get("period_mismatch") or dq.get("period_mismatch_note") or dq.get("period_coverage_note"))

                if has_truncation or has_partial or has_mismatch or period_defaulted:
                    clean_dq = {}
                    if dq.get("truncation_note"):
                        clean_dq["truncation_note"] = dq["truncation_note"]
                    if dq.get("has_more") is not None:
                        clean_dq["has_more"] = dq["has_more"]
                    if dq.get("is_partial_period") is not None:
                        clean_dq["is_partial_period"] = dq["is_partial_period"]
                    if dq.get("partial_year_note"):
                        clean_dq["partial_year_note"] = dq["partial_year_note"]
                    if dq.get("period_coverage_note"):
                        clean_dq["period_coverage_note"] = dq["period_coverage_note"]
                    if dq.get("period_mismatch_note"):
                        clean_dq["period_mismatch_note"] = dq["period_mismatch_note"]
                    
                    if period_defaulted:
                        defaulted_period = (isinstance(query_params, dict) and query_params.get("period")) or str(datetime.now().year)
                        clean_dq["period_note"] = f"No year specified — showing {defaulted_period} (latest available) data."

                    response["summary"] = {"data_quality": clean_dq}
                    response["summary_metrics"] = {"data_quality": clean_dq}

            # Forward citations if present
            if "citations" in trade_res and isinstance(trade_res["citations"], list) and len(trade_res["citations"]) > 0:
                response["citations"] = trade_res["citations"]
        
        if context.clarifications: response["clarifications"] = context.clarifications
        if context.errors: response["errors"] = context.errors

        # Generate suggestions dynamically if not already populated (e.g. by trade service)
        if not response.get("suggestion"):
            response["suggestion"] = []
            core_intents = {"hs_code_lookup", "calculation", "trade_query", "general"}
            current_intent_val = context.intent.value if context.intent else None
            
            should_generate = (
                current_intent_val in core_intents
                and context.status in {WorkflowStatus.COMPLETED, WorkflowStatus.CLARIFICATION_REQUIRED}
            )
            
            if should_generate and response.get("answer"):
                try:
                    service_query = self._get_service_query(context)
                    lang = context.metadata.get("language") or getattr(context, "language", "en")
                    result_payload = context.calculation_result or context.retrieval_result or context.trade_query_result
                    suggestions = self.suggestion_service.get_suggestions(
                        current_intent=current_intent_val,
                        rewritten_query=service_query,
                        session_context=context.session_context,
                        language=lang,
                        result_payload=result_payload,
                        nlu_entity=context.metadata.get("nlu_entity"),
                        has_nlu_entity=context.metadata.get("has_nlu_entity", False),
                    )
                    response["suggestion"] = suggestions
                except Exception as e:
                    logger.error(f"[{context.request_id}] Failed to generate suggestions: {e}", exc_info=True)

        # Always merge context-level metadata so service_latencies_s (and other
        # pipeline metadata) is available for every intent type, not just retrieval.
        if context.metadata:
            response["metadata"].update(context.metadata)

        # ===== UNIVERSAL FALLBACK FOR EMPTY / FAILED / ERROR RESPONSES ACROSS ALL SERVICES =====
        raw_answer = response.get("answer")
        raw_ans_str = str(raw_answer or "").strip().lower()
        is_error_or_empty = (
            not raw_answer
            or raw_ans_str in ("", "none", "no answer found", "null")
            or context.status == WorkflowStatus.FAILED
            or "validation error:" in raw_ans_str
            or "duty rates not found" in raw_ans_str
            or "error processing" in raw_ans_str
            or "failed to resolve" in raw_ans_str
        )

        if is_error_or_empty:
            error_detail = raw_answer or (context.errors[0] if context.errors else "No data or duty rates found.")
            friendly_response = None
            try:
                if self.llm_service and self.llm_service.is_available():
                    provider = self.llm_service.router.providers.get("gemini") or self.llm_service.router.providers.get("openrouter")
                    if provider and provider.is_available():
                        from prompts.dynamic_prompt_manager import DynamicPromptManager
                        prompt_mgr = DynamicPromptManager()
                        prompt = prompt_mgr.render(
                            "universal_error_fallback",
                            question=context.question,
                            error_detail=error_detail
                        )
                        llm_resp = await asyncio.to_thread(
                            provider.client.models.generate_content,
                            model=provider.model_name,
                            contents=prompt,
                        )
                        friendly_response = (llm_resp.text or "").strip()
            except Exception as e:
                logger.warning(f"[{context.request_id}] Universal LLM error fallback response generation failed: {e}")

            if friendly_response:
                response["answer"] = friendly_response
                response["message"] = friendly_response
            else:
                if "Duty rates not found" in str(error_detail) or "HS code" in str(error_detail):
                    fallback_msg = (
                        "I couldn't find specific duty rates for that product or HS code in our current database. "
                        "Please verify the HS code or describe the item in more detail (e.g., 'smartphones', 'laptops', 'motor cars') to attempt an automatic rate lookup."
                    )
                else:
                    fallback_msg = (
                        "I'm sorry, I couldn't complete your request at this time. "
                        "Please verify your query parameters (such as product name, HS code, or invoice value) and try again."
                    )
                response["answer"] = fallback_msg
                response["message"] = fallback_msg

            if context.intent == WorkflowIntent.CALCULATION:
                response["status"] = "clarification_required"
                if context.session_context:
                    context.session_context.set_pending_clarification(
                        candidate_intents=["calculation"],
                        rewritten_query=context.question
                    )

        return response

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try: return float(value)
        except (TypeError, ValueError): return default

    @staticmethod
    def _safe_probability(value: Any, default: float = 0.0) -> float:
        try: parsed = float(value)
        except (TypeError, ValueError): parsed = default
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _selected_index(candidates: List[Dict[str, Any]], selected_info: Dict[str, Any], selected_code: Optional[str]) -> int:
        if selected_code:
            for idx, candidate in enumerate(candidates):
                if candidate.get("hs_code") == selected_code: return idx
        try:
            idx = int(selected_info.get("index", 0))
            if 0 <= idx < len(candidates): return idx
        except (TypeError, ValueError): pass
        return 0 if candidates else -1
    

    
    async def _build_error_response(self, context: WorkflowContext) -> Dict[str, Any]:
        return {"request_id": context.request_id, "question": context.question, "status": "failed", "errors": context.errors, "latency_ms": context.latency_ms}
    
    def _format_missing_discriminator_message(self, product_category: str, missing_field: Optional[str]) -> str:
        messages = {
            "vehicle_engine": "— For vehicle classification, please specify the **engine type** (petrol/diesel/electric/hybrid) and **engine size** (cc/kW).",
            "vehicle_size": "— For vehicle classification, please specify the **engine size** (cc/kW/power rating).",
            "food_preservation": "— For food products, please specify the **preservation method** (fresh/frozen/dried/smoked/canned).",
            "textile_construction": "— For textiles, please specify the **construction type** (knitted/woven/crocheted).",
            "textile_fiber": "— For textiles, please specify the **fiber type** (cotton/wool/synthetic/polyester).",
        }
        return messages.get(missing_field, "Please provide more details to help with classification.")