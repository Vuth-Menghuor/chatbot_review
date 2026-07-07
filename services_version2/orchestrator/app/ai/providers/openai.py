"""OpenAI provider adapter placeholder."""

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str], model: str = "gpt-4o-mini", timeout: int = 30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_key)

    def classify_intent(self, question: str) -> Tuple[str, float, str]:
        raise NotImplementedError("OpenAI provider is not implemented in this workspace")

    def detect_currency(self, question: str) -> Tuple[Optional[str], float, str]:
        raise NotImplementedError("OpenAI provider is not implemented in this workspace")

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        raise NotImplementedError("OpenAI provider is not implemented in this workspace")

    async def summarize_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError("OpenAI provider is not implemented in this workspace")

    async def select_best_hs_code(self, query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError("OpenAI provider is not implemented in this workspace")

    async def rewrite_descriptions_batch(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raise NotImplementedError("OpenAI provider is not implemented in this workspace")
