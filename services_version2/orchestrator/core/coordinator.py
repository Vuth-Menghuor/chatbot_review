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

from ..infrastructure.cache_service import get_cache_service
from ..llm_service import OrchestratorLLMService, LLMServiceConfig, get_llm_service
from ..llm_first_layer.shims.intent_service import OrchestratorIntentService, IntentServiceConfig
from ..llm_first_layer import get_llm_first_layer_service as get_intent_service
from ..formatter_service import OrchestratorFormatterService, FormatterServiceConfig, get_formatter_service
from ..llm_first_layer.shims.rewriter_service import RewriterService, RewriterServiceConfig
from ..llm_first_layer import get_llm_first_layer_service as get_rewriter_service

from .workflow import (
    WorkflowExecutor,
    WorkflowContext,
    WorkflowIntent,
    WorkflowStatus,
)
from .timeout_config import (
    TimeoutConfig,
    get_timeout_config,
)

from ..llm_first_layer.shims.validator_service import extract_certificate_type
from .validators import get_validator, ValidationResult

logger = logging.getLogger(__name__)


async def detect_small_talk(query: str, llm_service=None, force_llm_fallback: bool = False) -> Optional[str]:
    """Detects if the query is small talk/casual/unrelated and provides a friendly response."""
    PREDEFINED_RESPONSES = {
        "greeting": "Hello! I'm here to help you with Cambodia customs and trade questions. How can I assist you today?",
        "goodbye": "Thank you for using GDCE ChatBot. Have a wonderful day ahead, and feel free to reach out anytime you need customs assistance!",
        "gratitude": "You're very welcome! If you have any more questions about imports, exports, or customs procedures, I'm here to help.",
        "casual": "I am doing well, thank you for asking! Ready to help you with any customs or trade questions you have.",
        "joke": "Why did the customs officer go to school? To learn how to classify himself! Let me know if you need help classifying actual goods.",
        "roast": "You must be an HS code, because you're incredibly complicated to classify.",
        "social": "Nice to meet you too! Let me know if there's anything about customs or trade you'd like to discuss.",
        "confirmation": "Got it! Please go ahead with your customs or trade-related question.",
        "identity": "I am the GDCE ChatBot, a specialized assistant designed to help you with Cambodia customs regulations, duty calculations, HS code lookups, and trade queries."
    }
    
    low = (query or "").strip().lower()
    norm = re.sub(r"[^\w\s]", "", low).strip()
    
    is_obvious_small_talk = False
    matched_category = "confirmation"
    
    if norm in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "howdy", "greetings", "tell me a joke"] or any(re.search(pat, norm) for pat in [r"\bhi+\b", r"\bhey+\b", r"\bhello+\b", r"\byo+\b"]):
        is_obvious_small_talk = True
        matched_category = "greeting"
    elif any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["thanks", "thank you", "appreciate"]):
        is_obvious_small_talk = True
        matched_category = "gratitude"
    elif any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["bye", "goodbye", "farewell", "have a good day", "have a nice day"]):
        is_obvious_small_talk = True
        matched_category = "goodbye"
    elif any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["nice to meet you", "pleasure to meet you", "glad to meet you"]):
        is_obvious_small_talk = True
        matched_category = "social"
    elif any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["how are you", "whats up", "how is your day", "hows your day", "hows it going", "how is it going"]):
        is_obvious_small_talk = True
        matched_category = "casual"
    elif any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["tell me a joke", "tell a joke", "make me laugh", "joke"]):
        is_obvious_small_talk = True
        matched_category = "joke"
    elif any(re.search(rf"\b{re.escape(w)}\b", norm) for w in ["roast me"]):
        is_obvious_small_talk = True
        matched_category = "roast"
    elif any(re.search(pat, norm) for pat in [
        r"\b(what|who)\s+are\s+you\b",
        r"\bwhat\s+is\s+your\s+(name|purpose)\b",
        r"\bwhat\s+(can|do)\s+you\s+do\b",
        r"\bare\s+you\s+(a\s+)?(bot|ai|robot|chatbot|assistant)\b",
        r"\btell\s+me\s+about\s+yourself\b",
        r"\bcapabilities\b",
        r"\bhow\s+can\s+you\s+help\b"
    ]):
        is_obvious_small_talk = True
        matched_category = "identity"

    if is_obvious_small_talk:
        return PREDEFINED_RESPONSES[matched_category]

    stripped_alpha = re.sub(r"[^a-z]", "", low)
    if stripped_alpha and len(stripped_alpha) <= 5 and not force_llm_fallback:
        return None

    if llm_service and llm_service.is_available():
        if force_llm_fallback:
            prompt = (
                "You are GDCE ChatBot, a specialized assistant for Cambodia customs regulations, duty calculations, HS code lookups, and trade queries. "
                "Acknowledge the user's message with a short, friendly, and engaging response (1-2 sentences). "
                "If the message is completely unrelated to customs or trade, politely guide them back to trade/customs topics.\n\n"
                f"User message: {query}\n\nResponse:"
            )
        else:
            prompt = (
                "Determine if the following user query is small talk, casual conversation, a joke/roast request, or a social remark.\n"
                "If it is, generate a friendly, brief, and engaging response (1-2 sentences) acknowledging it in the context of a Cambodia Customs and Trade assistant.\n"
                "If the query is NOT small talk, return ONLY the exact word 'FALSE'.\n\n"
                f"Query: {query}"
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
                    if not force_llm_fallback and (content.upper() == "FALSE" or "FALSE" in content.upper()[:10]):
                        return None
                    return content
        except Exception as e:
            logger.warning(f"LLM small talk response failed: {e}")

    if force_llm_fallback:
        return PREDEFINED_RESPONSES["greeting"]
        
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
    ):
        self.retrieval_client = retrieval_client
        self.general_client = general_client or retrieval_client
        self.calculator_client = calculator_client
        self.trade_data_client = trade_data_client
        self.first_layer_service = first_layer_service  
        
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
        self.policy_engine = policy_engine
        self.timeout_config = timeout_config or get_timeout_config()
        self.use_input_rewriter = use_input_rewriter
        logger.info(f" LLM abstraction layer initialized (input rewrite enabled: {use_input_rewriter})")
    
    async def process_query(self, question: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Processes an incoming user query through the orchestration pipeline.
        
        The execution flow is as follows:
        1. Context initialization & tracking.
        2. Query normalization & fast small-talk detection.
        3. Input validation & safety/scope boundary checks.
        4. Clarification resolution if the session was awaiting user input.
        5. Intent detection & core intent filtering.
        6. Proactive ask-back checks for ambiguous core queries.
        7. Context-aware input rewriting using session history.
        8. Microservice routing & dispatching (calculator, trade_data, retrieval).
        9. Session state updates and final response formatting.
        """
        # Step 1: Initialize a unique request ID and workflow tracking context
        from ..utils import standardize_hs_codes_in_text
        question = standardize_hs_codes_in_text(question)
        request_id = str(uuid.uuid4())
        context = WorkflowContext(
            request_id=request_id,
            question=question,
            session_id=session_id,
            original_input=question  
        )
         
        try:
            # Step 2: Perform light normalization (lowercase, stripping) for early classification matching
            normalized_question = self._light_normalize_query(question)
            context.metadata["normalized_input"] = normalized_question
            
            # Step 3: Fast-path check for predefined/casual small talk (greetings, gratitude, etc.)
            small_talk_response = await detect_small_talk(normalized_question, self.llm_service)
            if small_talk_response:
                context.intent = WorkflowIntent.SMALL_TALK
                context.status = WorkflowStatus.COMPLETED
                context.metadata["small_talk"] = True
                context.finalize()
                
                # Update session history with the small talk exchange if session context is active
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

            # Step 4: Clean up query (stripping excessive punctuation/whitespaces) for internal processing
            cleaned_question = self.workflow_executor.cleanup_query(question)
            original_query = cleaned_question
            context.cleaned_input = original_query

            # Step 5: Validate query formatting and check domain/safety scope boundaries
            validator = get_validator()
            validation_result = validator.validate_input(normalized_question)
            
            # If the query fails basic validation rules (e.g. policy checks), fail early
            if not validation_result.is_valid:
                context.add_error(validation_result.reason)
                context.status = WorkflowStatus.FAILED
                context.finalize()
                return {
                    "intent": "validation_error",
                    "status": "failed",
                    "error": validation_result.reason,
                    "metadata": {"latency_ms": context.latency_ms, "request_id": request_id, "validation_failed": True}
                }
            
            # If the query is out of the system's operational scope, handle gracefully as dynamic small talk
            if not validation_result.is_in_scope:
                context.metadata["scope_check"] = {
                    "in_scope": False,
                    "reason": validation_result.scope_reason,
                    "keywords": validation_result.scope_keywords_matched
                }
                logger.info(f"[{request_id}] Query is out of scope. Handling as small talk.")
                
                # Generate a dynamic conversational refusal or fallback response via the LLM
                small_talk_response = await detect_small_talk(normalized_question, self.llm_service, force_llm_fallback=True)
                
                context.intent = WorkflowIntent.SMALL_TALK
                context.status = WorkflowStatus.COMPLETED
                context.finalize()
                
                # Update session history with the fallback exchange
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
                        "request_id": request_id,
                        "scope_check": context.metadata["scope_check"]
                    }
                }
            
            context.metadata["validation_passed"] = True
            context.metadata["scope_keywords_detected"] = validation_result.scope_keywords_matched
            
            # Step 6: Load session history context if session tracking and rewriter are enabled
            if self.use_input_rewriter and session_id:
                try:
                    session_context = self.rewriter_service.get_or_create_session(session_id)
                    context.session_context = session_context
                except Exception as e:
                    logger.warning(f"[{request_id}] Session context unavailable: {e}")

            # Step 7: Clarification Resolution (Handling user reply to a previous ask-back question)
            if context.session_context and context.session_context.is_awaiting_clarification():
                try:
                    from ..llm_first_layer import get_llm_first_layer_service as get_ask_back_service
                    ask_back_svc = get_ask_back_service()
                    # Resolve which of the candidate intents the user meant based on their response
                    resolved_intent = ask_back_svc.resolve_from_user_response(
                        user_text=question,
                        candidate_intents=context.session_context.clarification_intents,
                    )
                    if resolved_intent:
                        try: locked_intent = WorkflowIntent(resolved_intent)
                        except ValueError: locked_intent = None
                        
                        # Retrieve the original pending query and merge it with the new clarification details
                        pending_query = context.session_context.resolve_clarification(resolved_intent)
                        merged_query = self._merge_pending_with_clarification(
                            pending_query=pending_query,
                            clarification_response=question,
                            resolved_intent=resolved_intent,
                        )
                        context.clarification_confidence = 0.90
                        
                        # Validate the merged query; if invalid, fall back to using the user's latest message only
                        if not self._validate_merged_query(merged_query, resolved_intent):
                            merged_query = question
                        
                        # Update the context query and clean/normalize it
                        context.question = merged_query
                        normalized_question = self._light_normalize_query(context.question)
                        original_query = self.workflow_executor.cleanup_query(context.question)
                        context.cleaned_input = original_query
                        
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

            # Step 8: Intent Classification & Safety Gates
            _intent_confidence: float = 1.0
            raw_detected_intent = None

            if context.skip_intent_detection and context.clarification_locked_intent:
                # Reuse the previously resolved and locked intent
                context.intent = context.clarification_locked_intent
                raw_detected_intent = context.intent
            else:
                # Classify intent and confidence scores
                context.intent, _intent_confidence = self.workflow_executor.detect_intent_with_confidence(normalized_question)
                raw_detected_intent = context.intent
                # Run security check safety gate to prevent malformed or risky intent transitions
                context.intent = self._apply_intent_safety_gate(context, original_query)

            # Step 9: Core Intent Filtering (Directing non-core/refusal intents to small talk fallback)
            if context.intent not in {
                WorkflowIntent.CALCULATION,
                WorkflowIntent.TRADE_QUERY,
                WorkflowIntent.HS_CODE_LOOKUP,
                WorkflowIntent.GENERAL
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

            # Step 10: Dynamic Clarification (Ask-Back) Triggering
            # If the user is engaged in a multi-turn session and the classification confidence is ambiguous,
            # proactively trigger a clarification flow to align user intent.
            _already_resolved = bool(context.metadata.get("clarification_resolved"))
            _turn_number = len(getattr(context.session_context, 'turns', [])) + 1 if context.session_context else 1
            if (context.session_context and _turn_number >= 2 and not _already_resolved):
                try:
                    from ..llm_first_layer import get_llm_first_layer_service as get_ask_back_service
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
                    if ask_back_result.should_ask_back:
                        # Set session state to await clarification from user
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
                            trigger_reason=ask_back_result.trigger_reason,
                        )
                except Exception as e:
                    logger.warning(f"[{request_id}] Ask-back check failed: {e}")

            # Step 11: Context-Aware Query Rewriting
            # Use conversation history to resolve pronouns or implied context in the query.
            # Skipping rewriting for TRADE_QUERY and HS_CODE_LOOKUP to ensure original keyword matching is preserved.
            context.rewritten_input = original_query
            rewrite_status = "skipped"
            rewrite_skip_reason = self._get_rewrite_skip_reason(intent=context.intent, rewriter_enabled=self.use_input_rewriter)
            context.rewrite_metadata = context.rewrite_metadata or {"rewrite_reason": "not_applied", "reason": "rewrite_disabled_or_skipped"}

            if (self.use_input_rewriter and raw_detected_intent != WorkflowIntent.TRADE_QUERY and raw_detected_intent != WorkflowIntent.HS_CODE_LOOKUP):
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
                        f"[{request_id}] 🔵 Input Rewriter: original='{original_query}' "
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
                        logger.info(f"[{request_id}] ⚠️ Input Rewriter validation rejected. Reverting to original query.")
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
                    "reason": (
                        "trade_query rule" if context.intent == WorkflowIntent.TRADE_QUERY
                        else "hs_code_lookup rule" if context.intent == WorkflowIntent.HS_CODE_LOOKUP
                        else "input_rewriter_disabled"
                    ),
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
            target_service = self._resolve_target_service(context.intent)

            # Perform the async microservice routing
            await self._route_query(context)
            
            # Step 13: Update session tracking with processed query info
            if self.use_input_rewriter and session_id and context.session_context:
                try:
                    # Detect and set product category & import/export mode in session
                    from .hs_classifier import detect_simple_product_category
                    category = detect_simple_product_category(context.original_input)
                    mode = "import" if "import" in context.original_input.lower() else "export" if "export" in context.original_input.lower() else None
                    
                    update_kwargs = {
                        "last_intent": context.intent.value if context.intent else None,
                    }
                    if context.detected_currency:
                        update_kwargs["currency"] = context.detected_currency
                    if category and category != "other":
                        update_kwargs["product_category"] = category
                    if mode:
                        update_kwargs["import_export_mode"] = mode
                        
                    self.rewriter_service.update_session_context(session_id, **update_kwargs)
                    answer_summary = "Query processed"
                    if context.retrieval_result and context.retrieval_result.get("documents"):
                        docs = context.retrieval_result.get("documents", [])
                        if docs:
                            answer_summary = f"Found {len(docs)} relevant documents"
                    context.session_context.add_turn(user_input=context.original_input, bot_response=answer_summary[:200])
                except Exception as e:
                    logger.warning(f"[{request_id}] Failed to update session: {e}")
            
            # Finalize context and build orchestrator response package
            context.finalize()
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
        return "retrieval"

    # Merge the pending query with the clarification query.
    def _merge_pending_with_clarification(self, pending_query: str, clarification_response: str, resolved_intent: str) -> str:
        try:
            # Store the main topic/entity from the previous unanswered question
            entity = None
            
            # Extract entity from the pending query if it contains "what about" or "about"
            if pending_query:
                pending_lower = pending_query.lower()
                # Case 1: What about toyota -> Extract "toyota"
                if "what about" in pending_lower:
                    entity = pending_lower.split("what about")[1].rstrip("?").strip()
                # Case 2: Tell me about rice -> Extract "rice"
                elif "about" in pending_lower:
                    entity = pending_lower.split("about")[1].rstrip("?").strip()
                else:
                    words = pending_lower.split()
                    entity = words[-1].rstrip("?").strip() if words else None
                if entity in ["a", "the", "an", ""]:
                    entity = None
                    
            # List of words that refer to previous context
            # Example: User: "its HS code", "its" refers to the previous entity
            pronouns = ["its", "it", "that", "this", "these", "those"]
            response_lower = clarification_response.strip().lower()
            pronoun_match = None
            for pronoun in pronouns:
                if response_lower.startswith(pronoun):
                    pronoun_match = pronoun
                    break
            
            
            # If user says: Previous: "What about Toyota?, then: "its HS code",  "its" in this case mean "Toyota"
            # Result: "Toyota HS code"
            if pronoun_match and entity:
                return clarification_response.replace(pronoun_match, entity, 1).strip()
            
            if clarification_response and clarification_response.strip() and entity:
                if entity.lower() not in clarification_response.lower():
                    return f"{entity} {clarification_response}"
            
            # If clarification looks longer than the old query, assume user provided a complete new query
            if clarification_response and clarification_response.strip():
                if len(clarification_response) > len(pending_query):
                    merged = clarification_response
                    if resolved_intent == "calculation" and not any(phrase in merged.lower() for phrase in ["calculate", "import tax", "duty", "tariff"]):
                        merged = f"Calculate {merged}"
                    return merged
            
            return pending_query if pending_query and pending_query.strip() else clarification_response or ""
        except Exception as e:
            logger.error(f"[MERGE] Unexpected error during merge: {str(e)}", exc_info=True)
            return clarification_response or ""

    def _validate_merged_query(self, merged_query: str, resolved_intent: str) -> bool:
        """
        Validates that a merged/combined query is substantive enough and contains 
        relevant keywords for the detected intent.
        """
        # Check 1: Query must exist, and be at least 5 characters long
        if not merged_query or not merged_query.strip() or len(merged_query.strip()) < 5:
            return False  
                
        # Check 2: If the intent is a calculation task, verify calculation-related keywords are present
        if resolved_intent == "calculation":
            calc_keywords = ["tax", "duty", "tariff", "import", "cif", "value", "calculate", "cost"]
            if not any(kw in merged_query.lower() for kw in calc_keywords): 
                return False

        # Check 3: If the intent is HS code lookup, verify HS code-related keywords are present
        if resolved_intent == "hs_code_lookup":
            hs_keywords = ["hs code", "hs-code", "tariff code", "code", "ahtn", "harmonized code"]

            # ACCEPT if either:
            # A) User explicitly mentions HS code keywords, OR
            # B) Text looks like a commercial/product description (naked description)
            has_explicit_hs_keywords = any(kw in merged_query.lower() for kw in hs_keywords)
            looks_commercial = self._looks_like_commercial_description(merged_query)

            if not (has_explicit_hs_keywords or looks_commercial): 
                return False

        return True


    def _looks_like_commercial_description(self, text: str) -> bool:
        """
        Structural heuristic to detect if text appears to be copied from a logistics sheet,
        shipping manifest, or commercial product listing. Uses pattern matching for 
        specifications, model codes, and domain-specific vocabulary.
        """
        if not text: 
            return False
        
        # Convert to lowercase for case-insensitive matching
        low = text.lower()
        
        # Pattern 1: Match specifications and technical units
        # Looks for patterns like: "500cc", "2000wh", "19 seats", "2024", "500g x 10", etc.
        spec_unit_pattern = re.compile(
            r"\b(?:\d+[\.\d]*\s*cc|cc\b|\d+[\.\d]*\s*(?:wh|kwh|v|ah)\b|\d+\s*seats?\b|\d+\s*wheels?\b|(?:19|20)\d{2}\b|\d+\s*(?:g|kg|ml|l|pcs|bags|ctn)\s*x\s*\d+)\b", 
            re.IGNORECASE
        )
        
        # Pattern 2: Match model codes and product identifiers
        # Looks for patterns like: "ABC123", "MODEL99XY", "(2023)", etc.
        model_code_pattern = re.compile(
            r"\b[A-Z0-9]{2,}[0-9][A-Z0-9]*\b|\b[A-Z][A-Z0-9]{3,}\b|\(\d+\)"
        )
        
        # Pattern 3: Dictionary of commercial/product-related keywords
        # Covers vehicles, food products, electronics, packaging, etc.
        commercial_words = {
            "new", "used", "moto", "auto", "electric", "hybrid", "plug", "diesel", "petrol", "lpg", "cng", 
            "hev", "bev", "phev", "ckd", "ikd", "cbp",  
            "sedan", "suv", "van", "truck", "bus", "wheel", "seat", "door", "battery",  
            "tea", "bag", "bags", "powder", "powdered", "whole", "rice", "food", "pack", "packs", "box",  
            "frozen", "fresh", "organic", "grade"  
        }
        
        # Check if the text contains specification patterns (e.g., "500cc", "2024")
        has_spec = bool(spec_unit_pattern.search(low))
        
        # Check if the text contains model codes or product identifiers
        has_model = bool(model_code_pattern.search(text))
        
        # Extract all words from text and check how many match commercial keywords
        words_set = set(re.findall(r"[a-z]+", low))  # Extract all alphabetic words
        descriptor_hits = len(words_set & commercial_words)  # Count matches
        
        # Return True if at least 2 out of 3 indicators are present
        return sum([has_spec, has_model, descriptor_hits >= 1]) >= 2


    def _apply_intent_safety_gate(self, context: WorkflowContext, original_query: str) -> WorkflowIntent:
        """
        Safety mechanism that can override or adjust the detected intent based on 
        additional analysis. Prevents false classifications and corrects intent misdetections.
        """
        # Get the intent that was already detected by earlier logic
        detected_intent = context.intent

        if detected_intent == WorkflowIntent.HS_CODE_LOOKUP:
            return detected_intent

        # For lower-confidence intents (GENERAL, UNCLASSIFIED),
        # perform additional analysis to see if we should reclassify
        if detected_intent in {WorkflowIntent.GENERAL, WorkflowIntent.UNCLASSIFIED}:
            # Use cleaned input if available, otherwise fall back to original query
            candidate_query = context.cleaned_input or original_query
            
            # Check if the query looks like a product lookup despite being classified differently
            if self._looks_like_short_product_lookup(candidate_query): 
                return WorkflowIntent.HS_CODE_LOOKUP
            
            # Check if the query looks like a trade data request
            if self._looks_like_trade_data_query(candidate_query): 
                return WorkflowIntent.TRADE_QUERY
        
        # No reclassification needed; return the original detected intent
        return detected_intent

    # Detects if query is asking for trade statistics/data (volume, flows, comparisons).
    def _looks_like_trade_data_query(self, query: str) -> bool:
        q_lower = (query or "").lower()
        disqualifiers = ["hs code", "tariff code", "classify", "classification", 
                        "calculate", "duty", "tax", "vat", "fee", "regulation", "procedure"]
        if any(token in q_lower for token in disqualifiers): 
            return False
        # check for required parameters (Trade data queries usually reference specific time periods)
        has_year = re.search(r"\b20\d{2}\b", q_lower) is not None
        # Core indicator that user is talking about trade movement
        has_trade_flow = re.search(r"\b(import|imports|imported|im|export|exports|exported|ex)\b", q_lower) is not None
        # Indicates comparison or bilateral trade ("from X to Y", "between A and B")
        has_relation = re.search(r"\b(from|to|between|with|vs|versus)\b", q_lower) is not None
        has_trade_term = re.search(r"\b(trade|volume|flow|shipment|shipping|cargo|freight|data)\b", q_lower) is not None
        
        return bool(has_year and ((has_trade_flow and has_relation) or has_trade_term))

    # Detects if query is a NAKED PRODUCT DESCRIPTION (no explicit HS code request).e.g, "500cc motorcycle, automatic, sedan style"
    def _looks_like_short_product_lookup(self, query: str) -> bool:
        normalized = (query or "").strip().lower()
        if not normalized: 
            return False
        disqualifiers = ["hs", "code", "classify", "classification", "calculate", "duty", "tax", "import", "export", "trade", "regulation", "policy", "procedure", "what is", "define", "explain", "how much", "between", "from", "to"]
        if any(token in normalized for token in disqualifiers): 
            return False
        if re.match(r"^(what|how|which|where|when|why|can|could|is|are|do|does)\b", normalized): 
            return False
        # Product descriptions are short (product specs, not essays)
        tokens = re.findall(r"[a-z0-9]+", normalized)
        if not tokens or len(tokens) > 6: 
            return False
        # Blocks casual chat/off-topic queries
        blocked_tokens = {"hello", "hi", "hey", "thanks", "please", "weather", "time", "date", "football", "soccer", "movie", "music", "recipe", "cook", "joke", "politics", "war", "crime", "hack", "hacking", "investment", "stock"}
        if any(token in blocked_tokens for token in tokens): 
            return False
        return True

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
        if intent == WorkflowIntent.TRADE_QUERY: 
            return "trade_query rule"
        if intent == WorkflowIntent.HS_CODE_LOOKUP: 
            return "hs_code_lookup skip_rewrite - retrieval service has own LLM spec extraction"
        return "rewrite_allowed"
    
    def _is_rewrite_valid(self, original_query: str, rewritten_query: str, intent: Optional[WorkflowIntent] = None) -> bool:
        """
        Validates that a rewritten query preserves the essential structure and meaning
        of the original query. Prevents over-aggressive rewrites that lose critical data.

        For GENERAL intent, only checks that the rewrite is non-empty — short follow-up
        queries like "what about it?" legitimately expand to much longer, low-overlap results.
        For all other intents, enforces structured token preservation and ≥50% token overlap.
        """
        # TOKENIZE both queries into comparable units
        # Extracts: words, numbers, structured identifiers (with dots/dashes). e.g,  "500cc" → ["500cc"]
        original_tokens = self._rewrite_tokens(original_query)
        rewritten_tokens = self._rewrite_tokens(rewritten_query)

        if not rewritten_tokens:
            return False

        # GENERAL intent: trust the LLM rewriter — only reject empty rewrites.
        # Short pronouns/follow-ups ("what about it?") expand naturally to low-overlap results.
        if intent == WorkflowIntent.GENERAL:
            return True

        """
        EXTRACT structured tokens from original
        "Structured" = contains digits OR has dots/dashes (codes, specs, years, versions)
        Examples: "500cc", "2024", "hs-code", "v1.0", "model-x3"
        These are critical identifiers that MUST be preserved
        """
        structured_tokens = {token for token in original_tokens if any(char.isdigit() for char in token) or "." in token or "-" in token}
        # check if the rewritten query contains all essential information
        if structured_tokens and not structured_tokens.issubset(set(rewritten_tokens)):
            return False
        # For calculation: how much of the original vocabulary appears in the rewrite?
        overlap = len(set(original_tokens) & set(rewritten_tokens)) / max(len(set(original_tokens)), 1)
        return overlap >= 0.5
    
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
        else: await self._handle_default(context)
    
    async def _handle_calculation(self, context: WorkflowContext):
        # Log the routing decision for debugging/tracing
        logger.info(f"[{context.request_id}] Routing to calculator service")
        try:
            # Guard: calculator service must be initialized
            # If not, fail fast with a clear error
            if not self.calculator_client:
                context.add_error("Calculator service not configured")
                context.status = WorkflowStatus.FAILED
                return
                
            cache = get_cache_service()
            # Determine which query string to use (priority: metadata override > cleaned > original)
            service_query = self._get_service_query(context)
            # Cache key includes intent type to avoid collision with other intents
            cached_result = cache.get_cached_response(service_query, intent="calculation")
            if cached_result:
                context.set_result("calculation", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return
            """
            Miss: compute timeout as the minimum of:
            - Intent-specific timeout (calculation queries might be slower than others)
            - Service-specific timeout (calculator service has its own SLA - Service Level Agreement)
            Take the stricter (smaller) timeout to prevent hanging
            """
            timeout_sec = min(self.timeout_config.get_intent_timeout(context.intent), self.timeout_config.get_service_timeout("calculator"))
            
            try:
                # Direct query to the calculator service, forwarding the query text
                result = await asyncio.wait_for(
                    self.calculator_client.query(question=service_query), timeout=timeout_sec
                )
                
                cache.cache_response(question=service_query, response=result, intent="calculation", ttl_seconds=2 * 3600, source="calculator")
                context.set_result("calculation", result)
                context.status = WorkflowStatus.COMPLETED

            except asyncio.TimeoutError:
                context.add_error(f"Calculator service timed out after {timeout_sec}s")
                context.status = WorkflowStatus.FAILED
        except Exception as e:
            logger.error(f"[{context.request_id}] Calculation failed: {e}")
            context.add_error(f"Calculator service error: {str(e)}")
            context.status = WorkflowStatus.FAILED
    
    async def _handle_trade_query(self, context: WorkflowContext):
        try:
            if not self.trade_data_client:
                context.add_error("Trade data service not configured")
                context.status = WorkflowStatus.FAILED
                return
            
            timeout_sec = min(self.timeout_config.get_intent_timeout(context.intent), self.timeout_config.get_service_timeout("trade_data"))
            
            try:
                result = await asyncio.wait_for(
                    self.trade_data_client.query(context.question), timeout=timeout_sec
                )
                context.set_result("trade_query", result)
                context.status = WorkflowStatus.COMPLETED
            except asyncio.TimeoutError:
                context.add_error(f"Trade data service timed out after {timeout_sec}s")
                context.status = WorkflowStatus.FAILED
        except Exception as e:
            context.add_error(f"Trade data service error: {str(e)}")
            context.status = WorkflowStatus.FAILED

    async def _handle_hs_code_lookup(self, context: WorkflowContext):
        """
        Routes directly to the retrieval service for HS code lookup.
        The retrieval service handles candidate ranking and generates a final_answer.
        The orchestrator simply passes that final_answer through to the response.
        """
        logger.info(f"[{context.request_id}] Routing to retrieval service for HS Lookup")
        try:
            if not self.retrieval_client:
                context.add_error("Retrieval service not configured")
                context.status = WorkflowStatus.FAILED
                return

            service_query = self._get_service_query(context)
            timeout_sec = min(
                self.timeout_config.get_intent_timeout(context.intent),
                self.timeout_config.get_service_timeout("retrieval")
            )

            cache = get_cache_service()
            cached_result = cache.get_cached_response(service_query, intent="hs_code_lookup")
            if cached_result:
                context.set_result("retrieval", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return

            try:
                result = await asyncio.wait_for(
                    self.retrieval_client.hs_code_lookup(
                        query=service_query,
                        top_k=5,
                        generate_answer=True,
                        hs_mode="best",
                        session_id=context.session_id
                    ),
                    timeout=timeout_sec
                )

                cache.cache_response(
                    question=service_query,
                    response=result,
                    intent="hs_code_lookup",
                    ttl_seconds=24 * 3600,
                    source="retrieval"
                )
                context.set_result("retrieval", result)
                context.status = WorkflowStatus.COMPLETED

            except asyncio.TimeoutError:
                context.add_error(f"HS code lookup service timed out after {timeout_sec}s")
                context.status = WorkflowStatus.FAILED
        except Exception as e:
            context.add_error(f"HS code lookup service error: {str(e)}")
            context.status = WorkflowStatus.FAILED
    
    async def _handle_definition(self, context: WorkflowContext):
        try:
            if not self.retrieval_client:
                context.add_error("Retrieval service not configured")
                context.status = WorkflowStatus.FAILED
                return
            
            timeout_sec = min(self.timeout_config.get_intent_timeout(context.intent), self.timeout_config.get_service_timeout("retrieval"))
            cache = get_cache_service()
            intent_key = "general"
            service_query = self._get_service_query(context)
            cached_result = cache.get_cached_response(service_query, intent=intent_key)
            if cached_result:
                context.set_result("retrieval", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return
            
            try:
                result = await asyncio.wait_for(
                    self.retrieval_client.general(query=service_query, top_k=5, generate_answer=True, session_id=context.session_id), timeout=timeout_sec
                )
                cache.cache_response(question=service_query, response=result, intent=intent_key, ttl_seconds=48*3600, source="retrieval")
                context.set_result("retrieval", result)
                context.status = WorkflowStatus.COMPLETED
            except asyncio.TimeoutError:
                context.add_error(f"Retrieval service timed out after {timeout_sec}s")
                context.status = WorkflowStatus.FAILED
        except Exception as e:
            context.add_error(f"Retrieval service error: {str(e)}")
            context.status = WorkflowStatus.FAILED
    
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
            try:
                result = await asyncio.wait_for(
                    self.general_client.general(query=service_query, top_k=5, generate_answer=True, session_id=context.session_id), timeout=timeout_sec
                )
                cache.cache_response(question=service_query, response=result, intent="general", ttl_seconds=48*3600, source="general")
                context.set_result("retrieval", result)
                context.status = WorkflowStatus.COMPLETED
            except asyncio.TimeoutError:
                context.add_error(f"General service timed out after {timeout_sec}s")
                context.status = WorkflowStatus.FAILED
        except Exception as e:
            context.add_error(f"General service error: {str(e)}")
            context.status = WorkflowStatus.FAILED
    
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
        
        # ===== DIRECT EXTRACT FOR RETRIEVAL/HS_CODE_LOOKUP RESULT =====
        if context.retrieval_result:
            response["answer"] = context.retrieval_result.get("final_answer", "No response generated by retrieval service.")
            
            # Forward standard citations directly from payload documents without manual text rebuilding
            documents = context.retrieval_result.get("documents", [])
            response["citations"] = [{"doc_id": d.get("id"), "snippet": (d.get("content", "") or d.get("metadata", {}).get("description", "")).strip()[:200], "score": d.get("score", 0), "source": d.get("source", "semantic")} for d in documents]
            response["metadata"] = {
                "semantic_count": context.retrieval_result.get("semantic_count", 0),
                "structured_count": context.retrieval_result.get("structured_count", 0),
                "total_count": context.retrieval_result.get("total_count", 0),
                "answer_source": context.retrieval_result.get("answer_source", "unknown")
            }
            if context.metadata:
                response["metadata"].update(context.metadata)
        
        if context.calculation_result:
            response["answer"] = (
                context.calculation_result.get("answer") or
                context.calculation_result.get("final_answer") or
                context.calculation_result.get("formatted_answer")
            )
            if not response["answer"]:
                total = context.calculation_result.get("total", 0)
                currency = context.calculation_result.get("currency", "KHR")
                response["answer"] = f"Total Import/Export Taxes and Duties: {total:,.0f} {currency}"
            response["metadata"].update(context.calculation_result.get("metadata", {}))
            if context.calculation_result.get("references"):
                response["citations"] = context.calculation_result.get("references", [])
        
        if context.trade_query_result:
            # Trade service response keys: message, suggestion, summary, table, visualization
            # Map "message" → "answer" (primary display text)
            response["answer"] = (
                context.trade_query_result.get("message") or
                context.trade_query_result.get("answer") or
                context.trade_query_result.get("final_answer") or
                "No response generated by trade service."
            )
            # Forward table and visualization unchanged
            if "table" in context.trade_query_result:
                response["table"] = context.trade_query_result["table"]
            if "visualization" in context.trade_query_result:
                response["visualization"] = context.trade_query_result["visualization"]
            # Forward suggestions (trade service key: "suggestion")
            if "suggestion" in context.trade_query_result:
                response["suggestions"] = context.trade_query_result["suggestion"]
            elif "suggestions" in context.trade_query_result:
                response["suggestions"] = context.trade_query_result["suggestions"]
            # Forward summary metrics (trade service key: "summary")
            if "summary" in context.trade_query_result:
                response["summary_metrics"] = context.trade_query_result["summary"]
            # Forward citations if present
            if "citations" in context.trade_query_result:
                response["citations"] = context.trade_query_result["citations"]
            # Merge any metadata from trade service response
            if "metadata" in context.trade_query_result and isinstance(context.trade_query_result["metadata"], dict):
                response["metadata"].update(context.trade_query_result["metadata"])
        
        if context.clarifications: response["clarifications"] = context.clarifications
        if context.errors: response["errors"] = context.errors
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