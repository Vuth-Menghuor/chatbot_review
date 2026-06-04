"""Configuration for the orchestrator LLM abstraction layer."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LLMServiceConfig:
    """Provider-neutral configuration for LLM tasks."""

    intent_provider: str = "ollama"
    currency_provider: str = "ollama"
    rewrite_provider: str = "ollama"
    summarization_provider: str = "gemini"
    hs_selection_provider: str = "gemini"

    fallback_order: List[str] = field(default_factory=lambda: ["gemini", "ollama"]) #if the primary provider fails, use gemini then ollama as fallback
    retries: int = 2 #total attempts = 1 primary + 2 retries = 3 attempts
    retry_backoff_seconds: float = 0.5 #request timeout to prevents hanging requests.

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout: int = 30

    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_timeout: int = 30

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout: int = 30

    temperatures: Dict[str, float] = field(
        default_factory=lambda: {
            "intent": 0.0,  #deterministic
            "currency": 0.1, 
            "rewrite": 0.2,  #slightly creativity
            "summarize": 0.2,
            "hs_selection": 0.0,
        }
    )
