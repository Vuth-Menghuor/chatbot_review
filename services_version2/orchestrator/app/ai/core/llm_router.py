"""Task router for the orchestrator LLM abstraction layer."""

from dataclasses import dataclass
from typing import Dict, List

from ...core.config import LLMServiceConfig
from ..providers.base import BaseLLMProvider
from ..providers.gemini import GeminiProvider
from ..providers.ollama import OllamaProvider
from ..providers.openai import OpenAIProvider
from .tasks import LLMTask

"""
The router:

    initializes all providers
    stores them in a registry
    maps tasks → providers
    builds fallback chains
"""

@dataclass
class RoutedProviders:
    primary: BaseLLMProvider
    fallback: List[BaseLLMProvider]


class LLMRouter:
    """Resolve the correct provider for each task and apply fallback order."""

    def __init__(self, config: LLMServiceConfig): #store configuration 
        self.config = config
        #create a provider registry/dictionary 
        self.providers: Dict[str, BaseLLMProvider] = { 
            "ollama": OllamaProvider(config.ollama_host, config.ollama_model, config.ollama_timeout),
            "gemini": GeminiProvider(config.gemini_api_key, config.gemini_model, config.gemini_timeout),
            # "openai": OpenAIProvider(config.openai_api_key, config.openai_model, config.openai_timeout),
        }

    def route(self, task: LLMTask) -> RoutedProviders:
        """Return the primary provider and fallback chain for a task."""
        primary_name = self._primary_provider_for_task(task)
        primary = self.providers[primary_name]
        fallback = [self.providers[name] for name in self.config.fallback_order if name != primary_name and name in self.providers]
        return RoutedProviders(primary=primary, fallback=fallback)

    def _primary_provider_for_task(self, task: LLMTask) -> str:
        if task == LLMTask.INTENT_CLASSIFICATION:
            return self.config.intent_provider
        if task == LLMTask.CURRENCY_DETECTION:
            return self.config.currency_provider
        if task == LLMTask.REWRITE:
            return self.config.rewrite_provider
        if task == LLMTask.SUMMARIZATION:
            return self.config.summarization_provider
        if task == LLMTask.HS_SELECTION:
            return self.config.hs_selection_provider
        return self.config.intent_provider
