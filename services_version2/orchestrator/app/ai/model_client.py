"""Facade exposing provider-neutral LLM operations to the orchestrator."""

#support async retires and asynce provider call
import asyncio
#Support failures/warnings
import logging
#Regex matching
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import LLMServiceConfig
from .core.llm_router import LLMRouter
from .core.tasks import LLMTask

logger = logging.getLogger(__name__)


@dataclass
class LLMTaskResult:
    """Normalized result with simple retry/fallback metadata."""

    value: Any #actual response from the provider (e.g. rewritten text, intent label, etc.)
    provider: str #which provider returned this result (e.g. "gemini", "ollama")
    attempts: int #how many retired were used
    fallback_used: bool = False #whether fallback provide was used
    
    """
    Example:
    LLMTaskResult(
        value="HS code is 8471",
        provider="openai",
        attempts=2,
        fallback_used=False
        )
    """


class OrchestratorLLMService:
    """
    Single interface for all orchestrator LLM tasks.

    This layer hides provider-specific clients and handles retries/fallbacks.
    """

    def __init__(self, config: Optional[LLMServiceConfig] = None):
        self.config = config or LLMServiceConfig() #use provided config or default
        self.router = LLMRouter(self.config) #create router object, deciding which is the primary and fallback providers for each task
        self._session_provider = self.router.providers[self.config.rewrite_provider] #store provider used for session management 

    def is_available(self) -> bool:
        return any(provider.is_available() for provider in self.router.providers.values())
    
    """
    Used for:
        conversation memory
        contextual rewriting
        tracking previous messages
    """

    def get_or_create_session(self, session_id: str):
        if hasattr(self._session_provider, "get_or_create_session"):
            return self._session_provider.get_or_create_session(session_id)
        raise RuntimeError("Session management is not available from the configured rewrite provider")


    def update_session_context(self, session_id: str, **kwargs: Any) -> None:
        if hasattr(self._session_provider, "update_session_context"):
            self._session_provider.update_session_context(session_id, **kwargs)
            return
        raise RuntimeError("Session management is not available from the configured rewrite provider")

    def classify_intent(self, question: str) -> Tuple[Any, float, str]:
        routed = self.router.route(LLMTask.INTENT_CLASSIFICATION) #router choose provider based on config and task type
        providers = [routed.primary] + routed.fallback #build list of providers
        last_error: Optional[Exception] = None

        for provider in providers:
            if not provider.is_available():
                continue

            for attempt in range(self.config.retries + 1): #retries provider if error occurs 
                try:
                    return provider.classify_intent(question)
                except Exception as exc:
                    last_error = exc
                    if attempt < self.config.retries:
                        continue
                    logger.warning(
                        f"LLM intent classification failed on provider={provider.name} after {attempt + 1} attempts: {exc}"
                    )

        raise RuntimeError(f"No available LLM provider could classify intent: {last_error}")

    """
    This currency detection return something like: ("USD", 0.98, "currency_detection")
    """

    def detect_currency(self, question: str) -> Tuple[Optional[str], float, str]:
        routed = self.router.route(LLMTask.CURRENCY_DETECTION) 
        providers = [routed.primary] + routed.fallback 
        last_error: Optional[Exception] = None

        for provider in providers:
            if not provider.is_available():
                continue

            for attempt in range(self.config.retries + 1): 
                try:
                    return provider.detect_currency(question)
                except Exception as exc:
                    last_error = exc
                    if attempt < self.config.retries:
                        continue
                    logger.warning(
                        f"LLM currency detection failed on provider={provider.name} after {attempt + 1} attempts: {exc}"
                    )

        raise RuntimeError(f"No available LLM provider could detect currency: {last_error}")

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        if self._is_explicit_hs_lookup_query(user_input): #Checks whether query already explicitly asks for HS code.
            return user_input, {
                "rewrite_reason": "hs_lookup_explicit",
                "confidence": 1.0,
                "intent_changed": False,
                "topic_switch": False,
                "rewritten": False,
            }

        result = await self._execute_with_fallback(
            LLMTask.REWRITE,
            "rewrite_input",
            user_input,
            context,
            intent_hint,
        )
        return result.value

    async def summarize_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        result = await self._execute_with_fallback(LLMTask.SUMMARIZATION, "summarize_text", text, context)
        return result.value

    #let the LLM decide the most relevant one
    async def select_best_hs_code(self, query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = await self._execute_with_fallback(LLMTask.HS_SELECTION, "select_best_hs_code", query, candidates)
        return result.value
    
    #Prompt LLM to rewrite the descriptions so that it can be user-friendly descriptions
    async def rewrite_descriptions_batch(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = await self._execute_with_fallback(LLMTask.HS_SELECTION, "rewrite_descriptions_batch", candidates)
        return result.value

    async def _execute_with_fallback(self, task: LLMTask, method_name: str, *args: Any) -> LLMTaskResult:
        routed = self.router.route(task)
        providers = [routed.primary] + routed.fallback
        last_error: Optional[Exception] = None

        for provider in providers:
            if not provider.is_available():
                continue

            for attempt in range(self.config.retries + 1):
                try:
                    method = getattr(provider, method_name)
                    value = method(*args)
                    if asyncio.iscoroutine(value):
                        value = await value
                    return LLMTaskResult(
                        value=value,
                        provider=provider.name,
                        attempts=attempt + 1,
                        fallback_used=provider is not routed.primary,
                    )
                except Exception as exc:
                    last_error = exc
                    if attempt < self.config.retries:
                        await asyncio.sleep(self.config.retry_backoff_seconds)
                    else:
                        logger.warning(
                            f"LLM task {task.value} failed on provider={provider.name} after {attempt + 1} attempts: {exc}"
                        )

        raise RuntimeError(f"No available LLM provider could handle task {task.value}: {last_error}")

    #Uses regex to detect explicit HS lookup questions.
    @staticmethod 
    def _is_explicit_hs_lookup_query(user_input: str) -> bool:
        """Return True when the query already explicitly asks for an HS code."""
        lowered = re.sub(r"\s+", " ", (user_input or "").strip()).lower()
        explicit_patterns = [
            r"^what(?:'s| is) the hs code for .+\??$",
            r"^what(?:'s| is) hs code for .+\??$",
            r"^what(?:'s| is) the hs code of .+\??$",
            r"^hs code for .+\??$",
            r"^please tell me the hs code for .+\??$",
            r"^i need the hs code for .+\??$",
        ]
        return any(re.match(pattern, lowered) for pattern in explicit_patterns)

    async def translate_to_english(self, text: str) -> str:
        result = await self._execute_with_fallback(
            LLMTask.TRANSLATION_TO_EN,
            "translate_to_english",
            text
        )
        return result.value

    async def translate_to_khmer(self, text: str) -> str:
        result = await self._execute_with_fallback(
            LLMTask.TRANSLATION_TO_KM,
            "translate_to_khmer",
            text
        )
        return result.value

    async def unified_first_layer_call(
        self,
        query: str,
        history: str = "",
        rolling_summary: str = "",
        context_str: str = ""
    ) -> Dict[str, Any]:
        provider = self.router.providers.get("gemini")
        if provider and provider.is_available() and hasattr(provider, "unified_first_layer_call"):
            return await provider.unified_first_layer_call(
                query=query,
                history=history,
                rolling_summary=rolling_summary,
                context_str=context_str
            )
        return {}




_llm_service_instance: Optional[OrchestratorLLMService] = None


def get_llm_service(config: Optional[LLMServiceConfig] = None) -> OrchestratorLLMService:
    """Get or create the singleton orchestrator LLM service."""
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = OrchestratorLLMService(config)
    return _llm_service_instance
