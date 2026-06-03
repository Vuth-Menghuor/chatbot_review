"""
Main facade for the unified LLM first layer service.

Exposes a single interface for validation, intent detection, ambiguity checking,
currency detection, and query rewriting.
"""

import logging
from typing import Optional, Any

from .config import LLMFirstLayerConfig
from .models import FirstLayerResult
from .pipeline import FirstLayerPipeline

logger = logging.getLogger(__name__)


class LLMFirstLayerService:
    """
    Unified first LLM layer service.
    
    Orchestrates:
    - Input validation
    - Intent detection (Gemini primary)
    - Ambiguity checking
    - Currency detection
    - Query rewriting (Gemini)
    
    All operations happen in one coordinated pipeline with minimal LLM calls.
    """

    def __init__(self, config: Optional[LLMFirstLayerConfig] = None):
        self.config = config or LLMFirstLayerConfig()
        self.pipeline = FirstLayerPipeline(self.config)
        logger.info("LLM First Layer Service initialized")

    def is_available(self) -> bool:
        """Check if the service is operational."""
        return self.pipeline.intent_service.is_available()

    async def process(
        self,
        query: str,
        request_id: str,
        session_context: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> FirstLayerResult:
        """
        Process a user query through the unified first LLM layer.
        
        This is the main entry point for the orchestrator.
        
        Args:
            query: User input query
            request_id: Correlation ID for request tracing
            session_context: Optional session context for multi-turn
            session_id: Optional session ID
            
        Returns:
            FirstLayerResult containing:
            - validation status
            - detected intent and confidence
            - ambiguity check result
            - detected currency
            - rewritten query (if applicable)
            - processing metadata
        """
        return await self.pipeline.process(
            query=query,
            request_id=request_id,
            session_context=session_context,
            session_id=session_id,
        )


# Singleton management
_first_layer_instance: Optional[LLMFirstLayerService] = None


def get_llm_first_layer_service(
    config: Optional[LLMFirstLayerConfig] = None,
) -> LLMFirstLayerService:
    """Get or create the singleton LLM first layer service."""
    global _first_layer_instance
    if _first_layer_instance is None:
        _first_layer_instance = LLMFirstLayerService(config)
    return _first_layer_instance
