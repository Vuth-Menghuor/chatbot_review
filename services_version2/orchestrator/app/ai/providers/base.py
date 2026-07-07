"""Base provider interface for orchestrator LLM tasks."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseLLMProvider(ABC):
    """Common provider contract."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    def classify_intent(self, question: str) -> Tuple[Any, float, str]:
        raise NotImplementedError

    def detect_currency(self, question: str) -> Tuple[Optional[str], float, str]:
        raise NotImplementedError

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        raise NotImplementedError

    async def summarize_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError

    async def select_best_hs_code(self, query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError

    async def rewrite_descriptions_batch(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def translate_to_english(self, text: str) -> str:
        raise NotImplementedError

    async def translate_to_khmer(self, text: str) -> str:
        raise NotImplementedError


class BaseFormatterProvider(ABC):
    """Base class for formatter providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is operational."""
        pass

    @abstractmethod
    async def format_response(
        self,
        response_text: str,
        intent: Any,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format response based on intent type.
        """
        pass


