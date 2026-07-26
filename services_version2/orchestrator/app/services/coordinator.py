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

from ..utils import extract_entity

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

# Shared lists of countries and prefix families to filter out non-product descriptions
_TRADE_COUNTRIES = frozenset([
    "cambodia", "vietnam", "thailand", "china", "laos", "myanmar", "malaysia", "singapore", 
    "indonesia", "philippines", "brunei", "japan", "korea", "usa", "america", "europe", 
    "india", "germany", "france", "uk", "united kingdom", "australia", "canada"
])

_NON_PRODUCT_PREFIXES = (
    "regulat",   # regulate, regulation, regulatory, regulator
    "procedur",  # procedure, procedures, procedural
    "document",  # document, documents, documentation, documented
    "certif",    # certificate, certification, certified
    "declar",    # declare, declaration, declarant
    "clearanc",  # clearance, clearances
)

# Product-spec clarification state machine constants
# Maximum number of spec follow-up merges before we give up and route
# the next user input as a fresh query.
MAX_PRODUCT_ASK_BACK_RETRIES = 2

# Stop words stripped when extracting expected terms from clarifying questions.
_CLARIFY_STOP_WORDS = frozenset([
    "is", "the", "a", "an", "or", "as", "and", "of", "for", "are", "does",
    "do", "was", "with", "its", "this", "that", "your", "it", "in", "to",
    "has", "have", "can", "will", "be", "if", "not", "from", "you", "how",
])

# Generic nouns that survive stop-word stripping but are too broad to be
# useful as merge-eligibility signals — e.g. "vehicle" in
# "Is the vehicle imported as CBU?" must not match a topic-switch like
# "looking for a vehicle export permit".
_CLARIFY_GENERIC_NOUNS = frozenset([
    "vehicle", "product", "item", "type", "unit", "specify", "details",
    "model", "specific", "question", "questions", "classification",
    "code", "codes", "tariff", "tariffs", "goods", "import", "export",
    "imported", "exported", "use", "used",
    # Generic parts and helper tokens from verbose questions (excluding body types like car/sedan)
    "wheel", "wheels", "drive", "built", "kits", "kit", "four", "two", "three", "one", "first", "second", "third",
    "number", "numbers", "option", "options", "select", "choice", "choices", "equipped",
    "completely", "knocked", "down", "fully",
])

# Category-specific technical discriminators: words that genuinely answer
# a spec question and cannot be mistaken for a new product name.
_SPEC_DISCRIMINATORS: Dict[str, frozenset] = {
    "vehicle": frozenset([
        "petrol", "diesel", "electric", "hybrid", "ev", "battery",
        "engine", "cc", "kw", "hp", "4wd", "cbu", "ckd",
    ]),
    "food": frozenset([
        "fresh", "frozen", "airtight", "salted", "dried", "smoked",
        "prepared", "preserved",
    ]),
    "textile": frozenset([
        "knitted", "woven", "crocheted", "wool", "synthetic",
        "cotton", "artificial",
    ]),
}

# Words that indicate the user already wrote a full question/statement,
# OR is making small talk — neither should be rewritten as an HS query.
_QUESTION_SIGNALS = frozenset([
    # Question words
    "what", "which", "where", "when", "who", "how", "why",
    "is", "are", "can", "does", "do", "tell", "find",
    # Domain keywords (already a trade/customs query)
    "hs", "code", "tariff", "import", "export", "classify",
    "calculate", "duty", "rate", "definition",
    # Greetings & farewells
    "hello", "hi", "hey", "hiya", "howdy",
    "bye", "goodbye", "farewell", "ciao",
    "good", "morning", "afternoon", "evening", "night",
    # Politeness / small-talk
    "thanks", "thank", "please", "sorry", "excuse",
    "yes", "no", "ok", "okay", "sure", "nope", "yep",
    "great", "awesome", "nice", "cool", "wow",
])


async def generate_small_talk_response(query: str, llm_service=None) -> str:
    """
    Generates a polite/friendly response for small talk, chitchat, or out-of-scope queries.
    Utilizes static predefined responses for common greetings to bypass LLM calls,
    and applies a strict scope guardrail prompt if an LLM call is required.
    """
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
    is_obvious_small_talk = False
    matched_category = "confirmation"
    
    # Static word-boundary matching and length limits
    if len(low) < 15:
        if any(re.search(rf"\b{pat}\b", low) for pat in ["hi", "hello", "hey", "yo", "greetings", "helo", "bello"]):
            is_obvious_small_talk = True
            matched_category = "greeting"
        elif any(re.search(rf"\b{pat}\b", low) for pat in ["thanks", "thank", "thank you", "appreciate"]):
            is_obvious_small_talk = True
            matched_category = "gratitude"
        elif any(re.search(rf"\b{pat}\b", low) for pat in ["bye", "goodbye", "farewell"]):
            is_obvious_small_talk = True
            matched_category = "goodbye"
            
    # Longer pattern checks (social, jokes, casual, capability checks)
    if not is_obvious_small_talk:
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in ["nice to meet you", "pleasure to meet you", "glad to meet you"]):
            is_obvious_small_talk = True
            matched_category = "social"
        elif any(re.search(rf"\b{re.escape(w)}\b", low) for w in ["how are you", "whats up", "how is your day", "hows your day", "hows it going", "how is it going"]):
            is_obvious_small_talk = True
            matched_category = "casual"
        elif any(re.search(rf"\b{re.escape(w)}\b", low) for w in ["tell me a joke", "tell a joke", "make me laugh", "joke"]):
            is_obvious_small_talk = True
            matched_category = "joke"
        elif any(re.search(rf"\b{re.escape(w)}\b", low) for w in ["roast me"]):
            is_obvious_small_talk = True
            matched_category = "roast"
        elif any(re.search(pat, low) for pat in [
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

    # Call LLM as a general-purpose conversational assistant.
    # Inject the current server datetime so date/time questions are answered correctly.
    if llm_service and llm_service.is_available():
        current_datetime = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %H:%M UTC")
        prompt = _prompt_manager.render(
            "generate_small_talk_response",
            query=query,
            current_datetime=current_datetime,
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
            logger.warning(f"LLM small talk generation failed: {e}")

    return PREDEFINED_RESPONSES["greeting"]


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
        self.policy_engine = policy_engine
        self.timeout_config = timeout_config or get_timeout_config()
        self.use_input_rewriter = use_input_rewriter
        logger.info(f" LLM abstraction layer initialized (input rewrite enabled: {use_input_rewriter})")
    
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
        if not stream and is_km:
            response["question"] = original_question
            if "metadata" not in response:
                response["metadata"] = {}
            response["metadata"]["language"] = "km"

            text_key = "answer"
            if "error" in response and not response.get("answer"):
                text_key = "error"

            english_text = response.get(text_key)
            if english_text and isinstance(english_text, str) and english_text.strip():
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

                    # Guard 1: Small talk exit check (authoritative signal)
                    if cache_intent == "small_talk":
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
                            # Resolve which of the candidate intents the user meant based on their response
                            resolved_intent = ask_back_svc.resolve_from_user_response(
                                user_text=question,
                                candidate_intents=context.session_context.clarification_intents,
                            )
                            if resolved_intent:
                                try: locked_intent = WorkflowIntent(resolved_intent)
                                except ValueError: locked_intent = None
                                
                                # Retrieve the original pending query and merge it with the new clarification details.
                                # Pass session_last_entity so _merge_pending_with_clarification can fall back
                                # to the turn-1 entity if the turn-2 fragment carried no entity of its own.
                                session_last_entity = getattr(context.session_context, 'last_entity', None)
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
            
            # If the query is out of the system's operational scope, route to SMALL_TALK
            if not validation_result.is_in_scope:
                context.metadata["scope_check"] = {
                    "in_scope": False,
                    "reason": validation_result.scope_reason,
                    "keywords": validation_result.scope_keywords_matched
                }
                logger.info(f"[{request_id}] Query is out of scope. Routing to small talk.")
                context.intent = WorkflowIntent.SMALL_TALK
                context.skip_intent_detection = True
            
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
                # Run security check safety gate to prevent malformed or risky intent transitions
                context.intent = self._apply_intent_safety_gate(context, original_query)

            # Step 10: Dynamic Clarification (Ask-Back) Triggering
            # Trigger ask-back if the intent detection confidence is below 0.75 (meaning the query is ambiguous),
            # or if it's a turn-2+ query that is not self-sufficient.
            _already_resolved = bool(context.metadata.get("clarification_resolved"))
            _turn_number = len(getattr(context.session_context, 'turns', [])) + 1 if context.session_context else 1
            
            should_ask_back = False
            trigger_reason = ""
            
            if not _already_resolved:
                if _intent_confidence < 0.60:
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
                    # Detect and set product category & import/export mode in session
                    from .hs_classifier import detect_simple_product_category
                    tracking_query = context.rewritten_input if rewrite_status == "applied" else (context.cleaned_input or context.original_input)
                    category = detect_simple_product_category(tracking_query)
                    mode = "import" if "import" in tracking_query.lower() else "export" if "export" in tracking_query.lower() else None

                    # ---- Two-turn state: populate last_intent / last_entity / last_*_query ----
                    # last_raw_query: pre-standardization text (for audit/logging only)
                    # last_normalized_query: post-standardization canonical form used by merge logic
                    # last_entity: core subject noun phrase extracted via shared utility
                    last_entity_val = extract_entity(tracking_query)
                    if not last_entity_val and context.session_context:
                        last_entity_val = getattr(context.session_context, 'last_entity', None)

                    update_kwargs = {
                        "last_intent": context.intent.value if context.intent else None,
                        "last_raw_query": question,          # original pre-standardization input
                        "last_normalized_query": tracking_query,  # post-standardization canonical form
                        "last_entity": last_entity_val,
                    }
                    if context.detected_currency:
                        update_kwargs["currency"] = context.detected_currency
                    if category and category != "other":
                        update_kwargs["product_category"] = category
                    if mode:
                        update_kwargs["import_export_mode"] = mode

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
    ) -> str:
        """
        Assemble a usable query out of an incomplete fragment + the user's
        chosen intent from the ask-back round-trip.

        Entity resolution priority:
        1. extract_entity(pending_query)    — entity named in turn-2 fragment
        2. session_last_entity              — entity from turn-1 (SessionContext.last_entity)
        3. extract_entity(clarification_response) — entity from clarification response
        4. fall back to pending_query as-is
        """
        try:
            # ---- Step 1: extract entity from the clarification response (the user's answer) ----
            entity = extract_entity(clarification_response) if clarification_response else None

            # ---- Step 2: fall back to the pending query fragment ----
            if entity is None and pending_query:
                entity = extract_entity(pending_query)

            # ---- Step 3: fall back to turn-1 entity held in session state ----
            if entity is None and session_last_entity:
                entity = session_last_entity

            # ---- Step 2.6: Perform pronoun replacement early ----
            response_lower = clarification_response.strip().lower()
            pronouns = ["its", "it", "that", "this", "these", "those"]
            pronoun_match = None
            for pronoun in pronouns:
                if response_lower.startswith(pronoun):
                    if len(response_lower) == len(pronoun) or response_lower[len(pronoun)].isspace() or response_lower[len(pronoun)] == '-':
                        pronoun_match = pronoun
                        break

            if pronoun_match and entity:
                clarification_response = clarification_response.replace(pronoun_match, entity, 1).strip()
                response_lower = clarification_response.lower()

            # Detect if user clarification response is just an intent keyword choice
            is_keyword_choice = False
            intent_whitelist_patterns = [
                r"^calculation$", r"^calculator$", r"^calculate$", r"^tax$", r"^duty$",
                r"^hs[-_\s]*code(?:[-_\s]*lookup)?$", r"^hs$", r"^code$", r"^lookup$",
                r"^classify$", r"^classification$",
                r"^trade[-_\s]*query$", r"^trade$", r"^trade[-_\s]*data$", r"^statistics$", r"^volume$",
                r"^general$", r"^general[-_\s]*question$", r"^definition$", r"^policy$", r"^procedure$"
            ]
            if any(re.match(pat, response_lower) for pat in intent_whitelist_patterns):
                is_keyword_choice = True

            # If user provided a longer, substantive new query rather than just a selection option,
            # we can use that query directly.
            if not is_keyword_choice and clarification_response and clarification_response.strip():
                if len(clarification_response) > len(pending_query or ""):
                    merged = clarification_response
                    if entity and entity.lower() not in merged.lower():
                        merged = f"{entity} {merged}"
                    if resolved_intent == "calculation" and not any(
                        phrase in merged.lower() for phrase in ["calculate", "import tax", "duty", "tariff"]
                    ):
                        merged = f"Calculate {merged}"
                    return merged

            # Otherwise, reconstruct the query based on the resolved intent and extracted entity
            product = entity or "goods"
            if resolved_intent == "calculation":
                cif_val = None
                currency = "USD"
                origin = "Thailand"
                if session_context:
                    # Scan backwards in session history to find the most recent calculation parameters
                    turns_to_check = []
                    if hasattr(session_context, "turns") and session_context.turns:
                        turns_to_check = [turn.get("user") or turn.get("user_input", "") for turn in reversed(session_context.turns)]
                    
                    last_norm = getattr(session_context, 'last_normalized_query', None)
                    if last_norm:
                        turns_to_check.insert(0, last_norm)
                        
                    for q in turns_to_check:
                        if not q:
                            continue
                        try:
                            from ..infrastructure.clients import CalculatorServiceClient
                            params = CalculatorServiceClient._parse_question_for_calculation(q)
                            if params.get("cif_value") is not None and params.get("origin_country"):
                                cif_val = params.get("cif_value")
                                currency = params.get("currency") or "USD"
                                origin = params.get("origin_country")
                                break
                        except Exception:
                            pass
                
                if cif_val is not None and origin:
                    cif_display = int(cif_val) if cif_val == int(cif_val) else cif_val
                    sym_map = {
                        "USD": "$", "KHR": "៛", "EUR": "€", "GBP": "£",
                        "CNY": "¥", "JPY": "¥", "THB": "฿", "VND": "₫",
                        "KRW": "₩", "INR": "₹"
                    }
                    cur_str = sym_map.get(currency, f"{currency} ")
                    return f"Calculate import tax for {product} {cur_str}{cif_display} from {origin}"
                else:
                    return f"Calculate import tax for {product}"

            elif resolved_intent == "hs_code_lookup":
                return f"What is the HS code for {product}?"

            elif resolved_intent == "trade_query":
                # Extract mode, country, year, or month from current turn and session history
                mode = None
                country_phrase = None
                year = None
                month = None

                if session_context and getattr(session_context, 'import_export_mode', None):
                    mode = session_context.import_export_mode

                texts_to_scan = []
                if clarification_response:
                    texts_to_scan.append(clarification_response)
                if pending_query:
                    texts_to_scan.append(pending_query)
                if session_context:
                    if getattr(session_context, 'last_normalized_query', None):
                        texts_to_scan.append(session_context.last_normalized_query)
                    if hasattr(session_context, "turns") and session_context.turns:
                        for turn in reversed(session_context.turns):
                            texts_to_scan.append(turn.get("user") or turn.get("user_input", ""))

                COUNTRIES = list(_TRADE_COUNTRIES)
                MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

                for t in texts_to_scan:
                    if not t:
                        continue
                    t_lower = t.lower()
                    
                    if not mode:
                        if "export" in t_lower:
                            mode = "export"
                        elif "import" in t_lower:
                            mode = "import"
                            
                    if not country_phrase:
                        country_pat = "|".join(COUNTRIES)
                        prep_match = re.search(r"\b(to|from|in|into|with|for)\s+(" + country_pat + r")\b", t_lower)
                        if prep_match:
                            country_phrase = prep_match.group(0)
                        else:
                            c_match = re.search(r"\b(" + country_pat + r")\b", t_lower)
                            if c_match:
                                country_name = c_match.group(1)
                                if mode == "export":
                                    country_phrase = f"to {country_name}"
                                elif mode == "import":
                                    country_phrase = f"from {country_name}"
                                else:
                                    country_phrase = f"with {country_name}"
                                    
                    if not year:
                        year_match = re.search(r"\b(20\d{2}|19\d{2})\b", t_lower)
                        if year_match:
                            year = year_match.group(1)
                            
                    if not month:
                        month_pat = "|".join(MONTHS)
                        month_match = re.search(r"\b(" + month_pat + r")\b", t_lower)
                        if month_match:
                            month = month_match.group(1)

                mode = mode or "import"
                query_parts = [f"What are the {mode} statistics for {product}"]
                if country_phrase:
                    # Title case country words for professional display
                    words = country_phrase.split()
                    if len(words) > 1:
                        words[1:] = [w.capitalize() for w in words[1:]]
                        country_phrase = " ".join(words)
                    else:
                        country_phrase = country_phrase.capitalize()
                    query_parts.append(country_phrase)
                
                time_parts = []
                if month:
                    time_parts.append(month.capitalize())
                if year:
                    time_parts.append(year)
                if time_parts:
                    query_parts.append("in " + " ".join(time_parts))
                
                return " ".join(query_parts) + "?"


            elif resolved_intent == "general":
                return f"Tell me about {product}"

            # Prepend entity to clarification response if missing fallback
            if clarification_response and clarification_response.strip() and entity:
                if entity.lower() not in clarification_response.lower():
                    return f"{entity} {clarification_response}"

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
        # - Case-sensitive: Pure alphabetical codes (must be uppercase) or parenthesized numbers
        # - Case-insensitive: Alphanumeric codes containing at least one digit (e.g., "m8", "abc123", "12v")
        model_code_pattern_case_sensitive = re.compile(
            r"\b[A-Z]{4,}\b|\(\d+\)"
        )
        model_code_pattern_case_insensitive = re.compile(
            r"\b[a-z0-9]{2,}[0-9][a-z0-9]*\b|\b[a-z][0-9]\b|\b[0-9][a-z]\b",
            re.IGNORECASE
        )
        
        # Pattern 3: Dictionary of commercial/product-related keywords
        # Covers vehicles, food products, electronics, packaging, etc.
        commercial_words = {
            "new", "used", "moto", "auto", "electric", "hybrid", "plug", "diesel", "petrol", "lpg", "cng", 
            "hev", "bev", "phev", "ckd", "ikd", "cbp",  
            "sedan", "suv", "van", "truck", "bus", "wheel", "seat", "door", "battery",  
            "tea", "bag", "bags", "powder", "powdered", "whole", "rice", "food", "pack", "packs", "box",  
            "frozen", "fresh", "organic", "grade",
            # Additional vehicle/product category terms
            "car", "sports", "competition", "salmon", "fillet", "fish", "meat", "seafood",
            "textile", "garment", "apparel", "clothing", "cotton", "wool", "polyester",
            "laptop", "phone", "tablet", "computer", "electronics"
        }
        
        # Check if the text contains specification patterns (e.g., "500cc", "2024")
        has_spec = bool(spec_unit_pattern.search(low))
        
        # Check if the text contains model codes or product identifiers
        has_model = bool(
            model_code_pattern_case_sensitive.search(text)
            or model_code_pattern_case_insensitive.search(text)
        )
        
        # Extract all words from text and check how many match commercial keywords
        words_set = set(re.findall(r"[a-z]+", low))  # Extract all alphabetic words
        descriptor_hits = len(words_set & commercial_words)  # Count matches
        
        # Return True if at least 2 out of 3 indicators are present, OR if there are multiple commercial descriptor hits
        return sum([has_spec, has_model, descriptor_hits >= 1]) >= 2 or descriptor_hits >= 2

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
            from .hs_classifier import detect_simple_product_category
            
            cleaned_query = self.workflow_executor.cleanup_query(query)
            category = detect_simple_product_category(query)
            mode = "import" if "import" in query.lower() else "export" if "export" in query.lower() else None
            last_entity_val = extract_entity(cleaned_query or query)

            update_kwargs = {
                "last_intent": intent_value,
                "last_raw_query": query,
                "last_normalized_query": cleaned_query,
                "last_entity": last_entity_val,
            }
            if detected_currency:
                update_kwargs["currency"] = detected_currency
            if category and category != "other":
                update_kwargs["product_category"] = category
            if mode:
                update_kwargs["import_export_mode"] = mode

            self.rewriter_service.update_session_context(session_id, **update_kwargs)
            session_context.add_turn(user_input=query, bot_response=answer_summary[:200])
        except Exception as e:
            logger.warning(f"Failed to update session for query {query}: {e}")

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
        # Word-boundary check for disqualifiers to avoid substring false positives (e.g. Codeine / code)
        disqualifiers = ["hs", "code", "classify", "classification", "calculate", "duty", "tax", "import", "export", "importing", "exporting", "trade", "regulation", "policy", "procedure", "what is", "define", "explain", "how much", "between", "from", "to"]
        if any(re.search(rf"\b{re.escape(tok)}\b", normalized) for tok in disqualifiers):
            return False
        if re.match(r"^(what|how|which|where|when|why|can|could|is|are|do|does)\b", normalized): 
            return False
        # Product descriptions are short (product specs, not essays)
        tokens = re.findall(r"[a-z0-9]+", normalized)
        if not tokens or len(tokens) > 6: 
            return False
        # Guard A: known build-format abbreviations are spec answers, not standalone product lookups.
        _BUILD_FORMAT_ABBREVS = {"cbu", "ckd", "skd"}
        if len(tokens) == 1 and tokens[0] in _BUILD_FORMAT_ABBREVS:
            return False
        # Blocks casual chat/off-topic queries (including repeated-char greeting typos like "hii", "heyyy")
        blocked_tokens = {"hello", "hi", "hey", "thanks", "please", "weather", "time", "date", "football", "soccer", "movie", "music", "recipe", "cook", "joke", "politics", "war", "crime", "hack", "hacking", "investment", "stock"}
        if any(token in blocked_tokens for token in tokens):
            return False
        # Catch greeting typos: "hii", "hiii", "heyyy", "heyy", "helloooo" etc.
        # These are strings that are just repetitions of a known greeting base character pattern.
        if re.match(r"^(h[aeiou]{2,}|hey+|hell[o]+|hi+)$", normalized):
            return False
        # Filter countries
        if any(token in _TRADE_COUNTRIES for token in tokens):
            return False
        # Filter non-product prefix families
        if any(token.startswith(_NON_PRODUCT_PREFIXES) for token in tokens):
            return False
        # Filter purely numeric queries (e.g. year filters like "2025")
        if all(token.isdigit() for token in tokens):
            return False
        return True

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
        """
        Step 2c: Attempt to merge an incoming user message with a saved product
        entity when the session is awaiting a spec clarification answer.

        Returns (question, normalized_question) — either the merged form or the
        original form (if any guard prevented merging), with all session state
        already updated.

        Guards applied in order:
          1. Small-talk / exit check — caches result so Step 3 doesn't re-call.
          2. Retry cap (MAX_PRODUCT_ASK_BACK_RETRIES).
          3. Dynamic relevance guard — input must overlap with expected_terms;
             falls back to _looks_like_short_product_lookup for "other" category.
          4. Merged-query validation via _validate_merged_query.
        """
        session = context.session_context
        stripped = question.strip()
        normalized = self._light_normalize_query(stripped)
        input_tokens = set(re.findall(r"[a-z0-9]+", normalized))

        # ---- Guard 1: Small talk / explicit exit ---------------------------------
        small_talk_resp = await detect_small_talk(normalized_question, llm_service=None)
        if small_talk_resp:
            logger.info(
                f"[{request_id}] [SPEC-MERGE] Small talk detected ('{stripped[:40]}') — "
                "resetting product clarification state."
            )
            # Cache so Step 3 skips its own detect_small_talk call.
            context.metadata["small_talk_response"] = small_talk_resp
            self._clear_product_clarification(session)
            return question, normalized_question

        # ---- Guard 2: Retry cap --------------------------------------------------
        if session.product_ask_back_count >= MAX_PRODUCT_ASK_BACK_RETRIES:
            logger.info(
                f"[{request_id}] [SPEC-MERGE] Retry cap reached "
                f"({session.product_ask_back_count}/{MAX_PRODUCT_ASK_BACK_RETRIES}) — "
                "treating as fresh query."
            )
            self._clear_product_clarification(session)
            return question, normalized_question

        # ---- Guard 3: Dynamic relevance check -----------------------------------
        expected_terms = set(session.clarification_expected_terms or [])
        overlap = input_tokens & expected_terms
        if not overlap:
            # Fallback: for "other" category with no derived expected terms,
            # accept the input as a spec answer (Guard 4 validates merged result).
            if not expected_terms:
                logger.info(
                    f"[{request_id}] [SPEC-MERGE] No expected terms — accepting '{stripped[:40]}' "
                    "as spec answer (Guard 4 validates the merged result)."
                )
            else:
                logger.info(
                    f"[{request_id}] [SPEC-MERGE] Input '{stripped[:40]}' has no overlap "
                    f"with expected terms {list(expected_terms)[:6]} — resetting, treating as fresh query."
                )
                self._clear_product_clarification(session)
                return question, normalized_question
        else:
            logger.info(
                f"[{request_id}] [SPEC-MERGE] Matched expected terms: {list(overlap)}"
            )

        # ---- Guard 4: Validate merged query -------------------------------------
        entity = session.clarification_entity or ""
        merged = f"{entity} {stripped}".strip()
        if not self._validate_merged_query(merged, "hs_code_lookup"):
            logger.info(
                f"[{request_id}] [SPEC-MERGE] Merged query '{merged[:60]}' failed "
                "validation — treating as fresh query."
            )
            self._clear_product_clarification(session)
            return question, normalized_question

        # ---- All guards passed — inject merged query ----------------------------
        logger.info(
            f"[{request_id}] [SPEC-MERGE] Merging '{entity}' + '{stripped}' "
            f"-> '{merged}' (round {session.product_ask_back_count + 1})"
        )
        session.product_ask_back_count += 1
        # Temporarily clear the flag; _handle_hs_code_lookup will re-set it if
        # the merged result is still generic.
        session.product_clarification_needed = False
        context.question = merged
        context.original_input = merged
        context.metadata["_spec_merge_done"] = True
        context.metadata["spec_merge_entity"] = entity
        context.metadata["spec_merge_answer"] = stripped
        session.last_entity = merged  # Fix 4: stable product ground truth for subsequent turns
        session._trigger_change()

        normalized_merged = self._light_normalize_query(merged)
        return merged, normalized_merged

    def _clear_product_clarification(self, session) -> None:
        """Reset all product-spec clarification state on the session."""
        session.product_clarification_needed = False
        session.clarification_entity = None
        session.clarification_last_query = None
        session.product_ask_back_count = 0
        session.clarification_expected_terms = []
        session._trigger_change()

    @staticmethod
    def _build_spec_expected_terms(
        clarifying_questions: Optional[list],
        category: str,
    ) -> list:
        """
        Build the list of allowed response tokens that Step 2c will accept on the
        next user turn as a legitimate spec answer.

        Combines:
          - Category base discriminators from _SPEC_DISCRIMINATORS.
          - Question-derived tokens (from the actual clarifying questions),
            minus stop words and generic nouns.
        """
        base = set(_SPEC_DISCRIMINATORS.get(category, frozenset()))
        if not clarifying_questions:
            return sorted(base)

        question_tokens: set = set()
        for q in clarifying_questions:
            for tok in re.findall(r"[a-z0-9]+", (q or "").lower()):
                if (
                    len(tok) > 2
                    and tok not in _CLARIFY_STOP_WORDS
                    and tok not in _CLARIFY_GENERIC_NOUNS
                ):
                    question_tokens.add(tok)

        return sorted(base | question_tokens)

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

    async def _handle_calculation(self, context: WorkflowContext):
        logger.info(f"[{context.request_id}] Routing to calculator service")
        try:
            if not self.calculator_client:
                context.add_error("Calculator service not configured")
                context.status = WorkflowStatus.FAILED
                return
                
            service_query = self._get_service_query(context)

            # Check if mandatory calculation parameters (CIF value / numeric financial amount) are missing
            cif_val = getattr(context.session_context, 'cif_value', None) if context.session_context else None
            q_lower = service_query.lower()
            has_numeric_val = bool(re.search(r'\d+(?:,\d{3})*(?:\.\d+)?', q_lower))
            has_cif_keyword = any(k in q_lower for k in ["cif", "usd", "$", "khr", "price", "value", "worth", "cost"])

            if not cif_val and not (has_numeric_val and has_cif_keyword):
                logger.info(f"[{context.request_id}] Calculation missing CIF value. Prompting user for clarification.")
                
                # Extract specific subject/product name dynamically from session context or query
                product_name = None
                if context.session_context:
                    product_name = (
                        getattr(context.session_context, 'clarification_entity', None)
                        or getattr(context.session_context, 'commercial_description', None)
                        or getattr(context.session_context, 'product_category', None)
                    )
                if not product_name:
                    cleaned_product = re.sub(
                        r"(?i)\b(calculate|compute|how|about|the|tax|taxes|duty|duties|import|export|for|cbu|ckd|hs|code)\b",
                        "",
                        service_query
                    ).strip()
                    cleaned_product = re.sub(r"\s+", " ", cleaned_product).strip()
                    product_name = cleaned_product if cleaned_product else "this product"

                context.set_result("calculation", {
                    "answer": (
                        f"To calculate the import duty and taxes for **{product_name}**, please provide the **CIF value** "
                        "(Cost, Insurance, and Freight invoice value in USD or KHR, e.g., `$80,000 USD`)."
                    ),
                    "clarification_required": True,
                    "missing_fields": ["cif_value"]
                })
                context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                return

            cache = get_cache_service()
            cached_result = cache.get_cached_response(service_query, intent="calculation")
            if cached_result:
                context.set_result("calculation", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return

            timeout_sec = min(self.timeout_config.get_intent_timeout(context.intent), self.timeout_config.get_service_timeout("calculator"))
            
            async def run_call():
                return await asyncio.wait_for(
                    self.calculator_client.query(question=service_query), timeout=timeout_sec
                )
                
            result = await self._execute_service_call(
                context=context,
                service_name="calculator",
                client_call_fn=run_call,
                request_payload={"question": service_query}
            )
            
            cache.cache_response(question=service_query, response=result, intent="calculation", ttl_seconds=2 * 3600, source="calculator")
            context.set_result("calculation", result)
            context.status = WorkflowStatus.COMPLETED

        except Exception as e:
            logger.error(f"[{context.request_id}] Calculation failed: {e}")
            context.add_error(f"Calculator service error: {str(e)}")
            context.status = WorkflowStatus.FAILED
    
    def _is_slot_fragment_reply(self, user_text: str, clarification_intents: list) -> bool:
        """
        Gated structural matcher that checks if user text is a parameter/slot fragment reply.
        Filters out full conversational questions and exit markers before evaluating slot patterns.
        """
        if not user_text:
            return False

        low = user_text.lower().strip()

        # 1. Discourse & Exit Markers
        exit_markers = [
            "never mind", "nevermind", "actually", "forget it", "cancel", "instead",
            "what documents", "how do i", "what changed", "where can i", "is there any"
        ]
        if any(marker in low for marker in exit_markers):
            return False

        # 2. Key-Value Parameter Syntax
        if any(kv in low for kv in ["partner country:", "flow:", "period:", "product:", "cif:"]):
            return True

        # 3. Word Count Bound (Slot answers are concise fragments)
        words = low.split()
        if len(words) > 6:
            return False

        # 4. Slot Pattern Matches for Active Intents
        if any(intent in {"trade_query", "trade_data"} for intent in clarification_intents):
            has_flow = any(re.search(rf"\b{f}\b", low) for f in ["import", "export", "imported", "exported", "imports", "exports", "flow"])
            partner_countries = [c for c in _TRADE_COUNTRIES if c != "cambodia"]
            has_country = any(re.search(rf"\b{re.escape(c)}\b", low) for c in partner_countries)
            has_period = bool(
                re.search(
                    r"\b(19|20)\d{2}\b|\bq[1-4]\b|\bquarter\s+[1-4]\b|\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b|\b(last|this|next)\s+(month|quarter|year)\b",
                    low
                )
            )
            has_product = bool(extract_entity(low))
            
            if has_flow or has_country or has_period or has_product:
                return True

        return False

    async def _generate_trade_clarification_message(
        self,
        query: str,
        missing_slots: List[str],
        product_name: str
    ) -> str:
        """Generates a friendly, conversational LLM message requesting missing mandatory trade parameters for trade queries."""
        missing_desc = ", ".join(missing_slots)
        fallback_msg = (
            f"To assist you with trade statistics for **{product_name}**, please specify the missing details: "
            + ", ".join(f"**{p}**" for p in missing_slots) + "."
        )

        if self.llm_service and self.llm_service.is_available():
            prompt = _prompt_manager.render(
                "generate_trade_clarification",
                query=query,
                product_name=product_name,
                missing_desc=missing_desc,
            )
            try:
                provider = self.llm_service.router.providers.get("gemini")
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
                logger.warning(f"LLM trade clarification generation failed: {e}")

        return fallback_msg

    async def _handle_trade_query(self, context: WorkflowContext):
        try:
            if not self.trade_data_client:
                context.add_error("Trade data service not configured")
                context.status = WorkflowStatus.FAILED
                return
            
            service_query = self._get_service_query(context)

            # Check for mandatory trade parameters across query and session history on trade query turns
            session_context = context.session_context
            texts_to_scan = [service_query]
            if session_context:
                if getattr(session_context, 'last_normalized_query', None):
                    texts_to_scan.append(session_context.last_normalized_query)
                if hasattr(session_context, "turns") and session_context.turns:
                    for turn in reversed(session_context.turns):
                        texts_to_scan.append(turn.get("user") or turn.get("user_input", ""))

            # Strip negated terms ("not Vietnam", "not import") before slot extraction
            def strip_negated_terms(text: str) -> str:
                if not text: return text
                cleaned = re.sub(r"(?i)\b(?:not|no|instead of|other than)\s+[a-z0-9\s-]+\b(?=,|$|\band\b|\bor\b|\bbut\b)", "", text)
                cleaned = re.sub(r"(?i)\b[a-z0-9\s-]+\s+instead\b", "", cleaned)
                return cleaned.strip()

            combined_text = " ".join(strip_negated_terms(t) for t in texts_to_scan if t).lower()

            # Slot 1: Product / Commodity entity
            product_entity = extract_entity(combined_text) or (getattr(session_context, 'last_entity', None) if session_context else None)
            
            # Slot 2: Flow (import/export)
            has_flow = any(f in combined_text for f in ["import", "export", "imported", "exported", "imports", "exports"])
            
            # Slot 3: Time Period (year, quarter, month, date range)
            has_time_period = bool(
                re.search(
                    r"\b(19|20)\d{2}\b|\bq[1-4]\b|\bquarter\s+[1-4]\b|\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b|\b(last|this|next)\s+(month|quarter|year)\b",
                    combined_text
                )
            )

            # Slot 4: Partner Country (excluding cambodia)
            partner_countries = [c for c in _TRADE_COUNTRIES if c != "cambodia"]
            has_partner_country = any(re.search(rf"\b{re.escape(c)}\b", combined_text) for c in partner_countries)

            # Check escape hatch signals ("whatever", "idk", "latest", "any") or max retries cap
            ask_back_count = getattr(session_context, 'ask_back_count', 0) if session_context else 0
            is_escape_hatch = any(term in service_query.lower() for term in ["whatever", "idk", "don't know", "dont know", "any", "latest", "default"]) or ask_back_count >= MAX_PRODUCT_ASK_BACK_RETRIES

            missing_slots = []
            if not product_entity:
                missing_slots.append("product")
            if not has_flow:
                missing_slots.append("flow")
            if not has_time_period:
                missing_slots.append("trade_period")
            if not has_partner_country:
                missing_slots.append("partner_country")

            EXPECTED_TERMS_MAP = {
                "product": ["commodity name", "HS code", "e.g. rice, coffee, motor vehicle"],
                "flow": ["import", "export"],
                "trade_period": ["month", "quarter", "year", "date range", "e.g. Q1 2026, 2025, last month"],
                "partner_country": ["trading partner country", "e.g. Thailand, China, Vietnam, USA"]
            }

            if missing_slots and not is_escape_hatch:
                product_name = product_entity or "the product"
                friendly_message = await self._generate_trade_clarification_message(
                    query=service_query,
                    missing_slots=missing_slots,
                    product_name=product_name
                )
                logger.info(f"[{context.request_id}] Trade query missing mandatory parameters: {missing_slots}. Prompting user with LLM message.")
                
                if session_context:
                    session_context.pending_clarification = True
                    session_context.clarification_intents = ["trade_query"]
                    session_context.clarification_entity = missing_slots
                    session_context.pending_rewritten_query = context.question
                    session_context.ask_back_count += 1
                    session_context._trigger_change()

                context.set_result("trade_query", {
                    "answer": friendly_message,
                    "clarification_required": True,
                    "missing_fields": missing_slots,
                    "metadata": {
                        "pending_clarification": True,
                        "clarification_entity": missing_slots,
                        "clarification_expected_terms": {s: EXPECTED_TERMS_MAP[s] for s in missing_slots if s in EXPECTED_TERMS_MAP},
                        "original_query": context.question,
                        "guard_triggered": "trade_mandatory_params"
                    }
                })
                context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                return

            # Clear pending clarification and reset ask_back_count on resolution / escape hatch execution
            if session_context:
                session_context.pending_clarification = False
                session_context.clarification_intents = []
                session_context.ask_back_count = 0
                session_context._trigger_change()

            timeout_sec = min(self.timeout_config.get_intent_timeout(context.intent), self.timeout_config.get_service_timeout("trade_data"))
            
            async def run_call():
                return await asyncio.wait_for(
                    self.trade_data_client.query(context.question), timeout=timeout_sec
                )
                
            result = await self._execute_service_call(
                context=context,
                service_name="trade_data",
                client_call_fn=run_call,
                request_payload={"question": context.question}
            )

            # Transparent escape hatch header if defaults were substituted
            if is_escape_hatch and missing_slots and result and isinstance(result, dict):
                disclosed_defaults = []
                if "flow" in missing_slots: disclosed_defaults.append("**Import**")
                if "trade_period" in missing_slots: disclosed_defaults.append("**2024 (latest year)**")
                if "partner_country" in missing_slots: disclosed_defaults.append("**All Countries**")
                if disclosed_defaults:
                    notice = f"_Showing trade statistics using assumed defaults: {', '.join(disclosed_defaults)}._\n\n"
                    orig_ans = result.get("final_answer") or result.get("answer") or ""
                    result["final_answer"] = notice + orig_ans
                    result["answer"] = notice + orig_ans

            context.set_result("trade_query", result)
            context.status = WorkflowStatus.COMPLETED
        except Exception as e:
            context.add_error(f"Trade data service error: {str(e)}")
            context.status = WorkflowStatus.FAILED

    async def _handle_hs_code_lookup(self, context: WorkflowContext):
        logger.info(f"[{context.request_id}] Routing to retrieval service for HS Lookup")
        try:
            if not self.retrieval_client:
                context.add_error("Retrieval service not configured")
                context.status = WorkflowStatus.FAILED
                return

            service_query = self._get_service_query(context)
            from ..utils import clean_hs_query_for_retrieval
            clean_query = clean_hs_query_for_retrieval(service_query)
            if self._looks_like_short_product_lookup(clean_query):
                service_query = f"what is hs code of {clean_query}"
                clean_query = clean_hs_query_for_retrieval(service_query)
                context.question = service_query
            logger.info(f"[{context.request_id}] Cleaned retrieval query: '{service_query}' -> '{clean_query}'")

            timeout_sec = min(
                self.timeout_config.get_intent_timeout(context.intent),
                self.timeout_config.get_service_timeout("retrieval")
            )

            cache = get_cache_service()
            cached_result = cache.get_cached_response(clean_query, intent="hs_code_lookup")
            if cached_result:
                context.set_result("retrieval", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return

            async def run_call():
                return await asyncio.wait_for(
                    self.retrieval_client.hs_code_lookup(
                        query=clean_query,
                        top_k=5,
                        generate_answer=True,
                        hs_mode="best",
                        session_id=context.session_id
                    ),
                    timeout=timeout_sec
                )

            result = await self._execute_service_call(
                context=context,
                service_name="retrieval",
                client_call_fn=run_call,
                request_payload={
                    "query": clean_query,
                    "top_k": 5,
                    "generate_answer": True,
                    "hs_mode": "best",
                    "session_id": context.session_id
                }
            )

            cache.cache_response(
                question=clean_query,
                response=result,
                intent="hs_code_lookup",
                ttl_seconds=24 * 3600,
                source="retrieval"
            )
            context.set_result("retrieval", result)
            context.status = WorkflowStatus.COMPLETED

            # ---- Product-spec clarification post-processing ----------------------
            # If retrieval flagged the result as generic (is_generic=True), save the
            # product entity and expected response vocabulary onto the session so the
            # next user turn can be merged automatically (Step 2c).
            # Only proceed if we have an active session to write to.
            if context.session_context:
                session = context.session_context
                is_generic = bool(result.get("is_generic"))
                current_round = getattr(session, "product_ask_back_count", 0)

                if is_generic and current_round < MAX_PRODUCT_ASK_BACK_RETRIES:
                    # Fix 1b/1c: Invalidate stale hs_code and last_entity on confirmed topic change
                    # Only run invalidation when NOT mid-spec-merge (Fix 1c for Guard 4 edge case)
                    spec_merge_done = context.metadata.get("_spec_merge_done", False)
                    if not getattr(session, "product_clarification_needed", False) and not spec_merge_done:
                        prev_entity = session.last_entity or ""
                        new_entity = context.original_input or ""
                        prev_tokens = set(re.findall(r"[a-z0-9]+", prev_entity.lower()))
                        new_tokens = set(re.findall(r"[a-z0-9]+", new_entity.lower()))
                        if prev_tokens and not (prev_tokens & new_tokens):
                            session.hs_code = None
                            session.last_entity = new_entity
                            logger.info(
                                f"[{context.request_id}] [FIX-1b] Topic change detected "
                                f"('{prev_entity}' → '{new_entity}') — cleared stale hs_code + last_entity."
                            )

                    # Entity: use original_input (pre-rewrite) on first round;
                    # use accumulated merged query on subsequent rounds.
                    if current_round == 0:
                        entity = extract_entity(context.original_input) or context.original_input
                    else:
                        entity = context.original_input

                    # Build expected-term vocabulary from actual clarifying questions.
                    clarifying_questions = result.get("clarifying_questions") or []
                    category = detect_simple_product_category(entity or "")
                    expected_terms = self._build_spec_expected_terms(clarifying_questions, category)

                    session.product_clarification_needed = True
                    session.clarification_entity = entity
                    session.clarification_last_query = context.original_input
                    session.clarification_expected_terms = expected_terms
                    session._trigger_change()
                    logger.info(
                        f"[{context.request_id}] [SPEC-MERGE] Result is generic — "
                        f"saved entity='{entity}', category='{category}', "
                        f"expected_terms={expected_terms[:8]}"
                    )
                else:
                    # Successful specific classification, cap reached, or not generic:
                    # clear any pending clarification state so the next turn starts fresh.
                    if getattr(session, "product_clarification_needed", False) or current_round > 0:
                        self._clear_product_clarification(session)
                        logger.info(
                            f"[{context.request_id}] [SPEC-MERGE] Specific result or cap reached "
                            "— cleared product clarification state."
                        )

                    # Fix 1a: Persist resolved hs_code on successful specific lookup
                    resolved_code = result.get("hs_code") or result.get("selected_code")
                    if not is_generic and resolved_code:
                        session.hs_code = resolved_code
                        session.last_entity = session.last_entity or context.original_input
                        session._trigger_change()

        except Exception as e:
            context.add_error(f"HS code lookup service error: {str(e)}")
            context.status = WorkflowStatus.FAILED
    
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
        """Generates a direct LLM parametric answer for general terminology/definition queries when RAG has no document info."""
        if self.llm_service and self.llm_service.is_available():
            prompt = _prompt_manager.render(
                "generate_parametric_definition",
                query=query,
            )
            try:
                provider = self.llm_service.router.providers.get("gemini")
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
                logger.warning(f"LLM parametric definition generation failed: {e}")
        return f"I could not find an official document reference for '{query}'. Please specify if you are looking for customs procedures, tariff classifications, or duty calculations."

    async def _handle_definition(self, context: WorkflowContext):
        try:
            if not self.general_client:
                context.add_error("General service not configured")
                context.status = WorkflowStatus.FAILED
                return
            
            timeout_sec = min(self.timeout_config.get_intent_timeout(context.intent), self.timeout_config.get_service_timeout("general"))
            cache = get_cache_service()
            intent_key = "general"
            service_query = self._get_service_query(context)
            cached_result = cache.get_cached_response(service_query, intent=intent_key)
            if cached_result:
                context.set_result("retrieval", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return
            
            async def run_call():
                return await asyncio.wait_for(
                    self.general_client.definition(query=service_query, top_k=5, generate_answer=True, session_id=context.session_id), timeout=timeout_sec
                )

            result = await self._execute_service_call(
                context=context,
                service_name="general_definition",
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

            cache.cache_response(question=service_query, response=result, intent=intent_key, ttl_seconds=48*3600, source="general")
            context.set_result("retrieval", result)
            context.status = WorkflowStatus.COMPLETED
        except Exception as e:
            context.add_error(f"General service error: {str(e)}")
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
        logger.info(f"[{context.request_id}] Routing to small talk handler")
        try:
            # Audit and warn if customs keywords are confidently classified as small_talk (Gap 3 Resolved)
            low = (context.question or "").lower()
            customs_keywords = ["duty", "tariff", "hs code", "atiga", "rcep", "import", "export", "calculate", "tax"]
            matched_kws = [kw for kw in customs_keywords if re.search(rf"\b{re.escape(kw)}\b", low)]
            if matched_kws:
                logger.warning(
                    f"[{context.request_id}] [MONITOR] Query with customs keywords {matched_kws} "
                    f"was routed to small_talk: '{context.question}'"
                )

            # Check if already cached in metadata (e.g. from _try_merge_product_spec)
            small_talk_response = context.metadata.get("small_talk_response")
            if not small_talk_response:
                small_talk_response = await generate_small_talk_response(context.question, self.llm_service)
            
            context.set_result("small_talk", {"answer": small_talk_response})
            context.status = WorkflowStatus.COMPLETED
        except Exception as e:
            logger.error(f"[{context.request_id}] Small talk handler failed: {e}")
            context.add_error(f"Small talk service error: {str(e)}")
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
        
        if context.small_talk_result:
            response["answer"] = context.small_talk_result.get("answer")
            if "metadata" in context.small_talk_result and isinstance(context.small_talk_result["metadata"], dict):
                response["metadata"].update(context.small_talk_result["metadata"])
        
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
            if isinstance(context.retrieval_result.get("metadata"), dict):
                response["metadata"].update(context.retrieval_result["metadata"])
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

        # Generate suggestions dynamically if not already populated (e.g. by trade service)
        if not response.get("suggestions"):
            response["suggestions"] = []
            core_intents = {"hs_code_lookup", "calculation", "trade_query", "general"}
            current_intent_val = context.intent.value if context.intent else None
            
            should_generate = (
                current_intent_val in core_intents
                and context.status == WorkflowStatus.COMPLETED
            )
            
            if should_generate and response.get("answer"):
                try:
                    service_query = self._get_service_query(context)
                    suggestions = self.suggestion_service.get_suggestions(
                        current_intent=current_intent_val,
                        rewritten_query=service_query,
                        session_context=context.session_context
                    )
                    response["suggestions"] = suggestions
                except Exception as e:
                    logger.error(f"[{context.request_id}] Failed to generate suggestions: {e}", exc_info=True)

        # Always merge context-level metadata so service_latencies_s (and other
        # pipeline metadata) is available for every intent type, not just retrieval.
        if context.metadata:
            response["metadata"].update(context.metadata)

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