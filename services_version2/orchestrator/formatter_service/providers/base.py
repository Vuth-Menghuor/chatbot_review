"""Base provider interface for formatting service."""
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from ..core.models import FormatterIntent

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
        intent: FormatterIntent,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format response based on intent type.
        
        Args:
            response_text: Raw response from service
            intent: Type of response (calculation, retrieval, etc.)
            original_question: User's original question
            context: Additional context
            
        Returns:
            Formatted response
        """
        pass
