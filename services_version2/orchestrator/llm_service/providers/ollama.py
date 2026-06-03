"""Ollama provider adapter for intent, rewrite, and summarization tasks."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, host: str, model: str, timeout: int = 30):
        from ...llm_first_layer.shims.rewriter_service import get_rewriter_service, RewriterServiceConfig
        from ...llm_first_layer.shims.intent_service import get_intent_service, IntentServiceConfig

        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

        intent_config = IntentServiceConfig(llm_host=self.host, llm_model=model, timeout=timeout)
        self.intent_detector = get_intent_service(intent_config)

        rewriter_config = RewriterServiceConfig(
            ollama_host=self.host,
            ollama_model=model,
            ollama_timeout=timeout,
        )
        self._rewriter_service = get_rewriter_service(rewriter_config)

    def is_available(self) -> bool:
        return True

    def classify_intent(self, question: str) -> Tuple[Any, float, str]:
        intent, confidence, reasoning = self.intent_detector.detect_intent(question)
        return self._map_intent(intent), confidence, reasoning

    def detect_currency(self, question: str) -> Tuple[Optional[str], float, str]:
        """Detect currency from user query using Intent Service."""
        return self.intent_detector.detect_currency(question)

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        return await self._rewriter_service.rewrite_input(
            user_input,
            context=context,
            intent_hint=intent_hint,
        )

    async def summarize_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        prompt = (
            "Summarize the following text in 3 concise bullet points. "
            "Keep it factual and do not add new details.\n\n"
            f"Text: {text}"
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False, "temperature": 0.2},
                )
                response.raise_for_status()
                payload = response.json()
                return payload.get("response", "").strip() or text
        except Exception as e:
            logger.warning(f"Ollama summarization failed: {e}")
            return text

    async def select_best_hs_code(self, query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not candidates:
            return {
                "selected_code": None, 
                "confidence": 0.0, 
                "reason": "No candidates", 
                "index": -1,
                "top_3_candidates": []
            }
        best = max(candidates, key=lambda item: item.get("score", 0))
        return {
            "selected_code": best.get("hs_code"),
            "confidence": best.get("score", 0.0),
            "reason": "Ollama fallback selected by score ranking",
            "index": candidates.index(best),
            "top_3_candidates": candidates[:3]  # ← Return top 3 by score
        }

    async def rewrite_descriptions_batch(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return candidates

    async def extract_trade_parameters(self, question: str) -> Dict[str, Any]:
        raise NotImplementedError("Ollama does not support trade parameter extraction")

    def get_or_create_session(self, session_id: str):
        return self._rewriter_service.get_or_create_session(session_id)

    def update_session_context(self, session_id: str, **kwargs: Any) -> None:
        self._rewriter_service.update_session_context(session_id, **kwargs)

    @staticmethod
    def _map_intent(intent: Any) -> str:
        value = getattr(intent, "value", intent)
        return str(value)
