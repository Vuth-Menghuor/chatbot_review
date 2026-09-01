"""Facade exposing provider-neutral formatting operations to the orchestrator."""

import logging
from typing import Optional, Dict, Any

from ..core.config import FormatterServiceConfig
from .core.models import FormatterIntent
from .providers.ollama import OllamaFormatterProvider
from .providers.gemini import GeminiFormatterProvider

logger = logging.getLogger(__name__)

"""
The service:

    1. Receives raw answer
    2. Detects response type (intent)
    3. Adds context/citations
    4. Sends everything to an LLM provider (like Ollama)
    5. Gets back a polished response
    6. Returns it to orchestrator
"""

class OrchestratorFormatterService:
    """
    Single interface for all orchestrator formatting tasks.
    
    This layer hides provider-specific clients.
    """

    def __init__(self, config: Optional[FormatterServiceConfig] = None):
        self.config = config or FormatterServiceConfig()
        
        # Initialize available providers based on config
        self.providers = {}
        
        # Initialize Gemini provider if configured
        if self.config.provider == "gemini" or (self.config.gemini_api_key or self.config.gemini_model):
            try:
                self.providers["gemini"] = GeminiFormatterProvider(self.config)
                logger.info("Gemini formatter provider initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini formatter provider: {e}")
        
        # Initialize Ollama provider (fallback/legacy)
        if self.config.provider == "ollama" or "gemini" not in self.providers:
            try:
                self.providers["ollama"] = OllamaFormatterProvider(self.config)
                logger.info("Ollama formatter provider initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Ollama formatter provider: {e}")
        
        # Set active provider
        if self.config.provider in self.providers:
            self._provider = self.providers[self.config.provider]
        elif "gemini" in self.providers:
            logger.info(f"Configured provider '{self.config.provider}' not available, using Gemini")
            self._provider = self.providers["gemini"]
        elif "ollama" in self.providers:
            logger.info(f"Configured provider '{self.config.provider}' not available, using Ollama")
            self._provider = self.providers["ollama"]
        else:
            logger.warning("No formatter providers available")
            self._provider = None

    def is_available(self) -> bool:
        """Check if formatter service is operational."""
        if not getattr(self.config, "enabled", True):
            return False
        return self._provider is not None and self._provider.is_available()

    def enable(self):
        """Enable formatting."""
        self.config.enabled = True
        logger.info("Formatter service enabled")

    def disable(self):
        """Disable formatting."""
        self.config.enabled = False
        logger.info("Formatter service disabled")



    async def format_response_stream(
        self,
        base_answer: str,
        question: str,
        intent: str,
        context: Any = None,
        citations: Optional[list] = None,
    ):
        """
        Stream the formatted response using the configured provider with
        mid-stream fallback protection.

        - If Gemini fails BEFORE the first token is yielded (sent_any=False),
          we transparently fall back to the Ollama provider.
        - If Gemini fails AFTER tokens have already been sent (sent_any=True),
          we re-raise so the endpoint can emit an SSE error event and stop;
          starting Ollama from scratch at this point would garble the output.
        """
        if not self.is_available():
            yield base_answer
            return

        has_final_answer = False
        if isinstance(context, dict):
            metadata = context.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("has_final_answer"):
                has_final_answer = True
            elif context.get("has_final_answer"):
                has_final_answer = True

        if intent.lower() in ('general', 'definition', 'policy', 'policy_query') and has_final_answer:
            yield base_answer
            return

        intent_map = {
            'calculation': FormatterIntent.CALCULATION,
            'retrieval': FormatterIntent.RETRIEVAL,
            'trade_query': FormatterIntent.TRADE_QUERY,
            'policy': FormatterIntent.GENERAL,
            'policy_query': FormatterIntent.GENERAL,
            'definition': FormatterIntent.GENERAL,
            'general': FormatterIntent.GENERAL,
            'hs_code_lookup': FormatterIntent.HS_CODE_LOOKUP,
            'hs_code': FormatterIntent.HS_CODE_LOOKUP,
        }
        formatter_intent = intent_map.get(intent.lower(), FormatterIntent.GENERAL)

        merged_context: Dict[str, Any] = {}
        if isinstance(context, dict):
            merged_context.update(context)
        elif context is not None:
            merged_context['legacy_context'] = context
        if citations:
            merged_context['citations'] = citations

        sent_any = False
        try:
            async for chunk in self._provider.format_response_stream(
                response_text=base_answer,
                intent=formatter_intent,
                original_question=question,
                context=merged_context,
            ):
                sent_any = True
                yield chunk
        except Exception as e:
            logger.warning(f"Active formatter provider streaming failed: {e}")
            if not sent_any:
                # No tokens delivered yet — safe to restart with Ollama fallback
                if getattr(self._provider, "name", "") == "gemini" and "ollama" in self.providers:
                    try:
                        logger.info("No tokens sent yet. Falling back to local LLM (Ollama)...")
                        async for chunk in self.providers["ollama"].format_response_stream(
                            response_text=base_answer,
                            intent=formatter_intent,
                            original_question=question,
                            context=merged_context,
                        ):
                            yield chunk
                        return
                    except Exception as fallback_err:
                        logger.error(f"Ollama fallback streaming failed: {fallback_err}")
                # Both providers failed before first token — yield raw answer
                yield base_answer
            else:
                # Tokens already sent — cannot safely restart; propagate so the
                # endpoint emits an SSE error event and closes the stream.
                logger.error("Failure mid-stream after tokens sent. Propagating to emit error event.")
                raise


_formatter_service_instance: Optional[OrchestratorFormatterService] = None

def get_formatter_service(config: Optional[FormatterServiceConfig] = None) -> OrchestratorFormatterService:
    """Get or create the singleton orchestrator formatter service."""
    global _formatter_service_instance
    if _formatter_service_instance is None:
        _formatter_service_instance = OrchestratorFormatterService(config)
        logger.info("Initialized OrchestratorFormatterService singleton")
    return _formatter_service_instance


"""
Note:
1. The Base Layer (calculation_formatter.py) ALWAYS runs first. It takes the raw math from the calculator and safely constructs a reliable text-based table.

2. The System checks if Ollama is online. If Ollama is turned off, crashes, or times out, the system stops here and simply gives the user the text from calculation_formatter.py. That's why it is the "fallback"—it guarantees the chatbot never breaks just because the AI model is busy.

3. The Polish Layer (ollama.py) takes over (Primary). If Ollama is online, the system hands the text from Step 1 over to ollama.py. ollama.py acts as the primary formatter by doing two things:

It passes the HS Code description through the LLM to make it easier to read (_format_hs_description).
It completely rebuilds the table to include the newly improved AI description, and then sends that as the final answer to the user.
Because we just updated both files, the DATA SOURCES section will now be perfectly accurate regardless of whether the user sees the final LLM-polished version or the safety fallback version!
"""